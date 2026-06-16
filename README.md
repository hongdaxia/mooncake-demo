# Mooncake 上手 Demo（中文详解）

本目录是一套循序渐进的小 demo，帮助你从零熟悉 **Mooncake**，并在装好 `sglang` + `mooncake` 的环境里真正跑起来。

> 运行前提：
> - 先自行激活装好 `sglang` + `mooncake` 的 conda 环境，例如 `conda activate <你的环境名>`。
> - 默认只使用 **前 4 张 GPU（卡 0/1/2/3）** —— 已在 `env.sh` 里通过 `CUDA_VISIBLE_DEVICES=0,1,2,3` 限制，可按需修改。
> - 模型路径在 `env.sh` 的 `MODEL_PATH` 里配置，默认 `/home/Llama-3.1-8B-Instruct`，请改成你自己的模型目录。

---

## 一、Mooncake 是什么？

Mooncake 是一套 **以 KVCache 为中心** 的大模型推理基础设施。一句话：
> 把推理时算出来的 KVCache 从“只能待在 GPU 显存里”解放出来，让它可以下沉到 DRAM、外部存储，并能在不同进程/机器之间高速共享与复用。

它由几个组件构成（本 demo 会逐个接触到）：

| 组件 | 角色 | 类比 |
|------|------|------|
| **Transfer Engine（传输引擎）** | 最底层的“数据搬运工”，在进程/机器间用 RDMA/TCP/NVLink 高速搬运一段内存 | 高速快递 |
| **Mooncake Store（分布式 KV 存储）** | 面向用户的高层 API：`put/get` 对象，数据存放在各节点贡献的内存池里 | 分布式大字典 / Redis |
| **Master（主节点）** | 全局目录与调度：记录每个 key 在哪、管理副本/租约/淘汰 | 目录服务 |
| **Metadata Server（元数据服务）** | 传输引擎用它交换各节点的网络连接信息（可用 etcd 或自带 HTTP 版） | 通讯录 |

它最典型的两个用途：
1. **前缀复用（Prefix Cache / HiCache）**：把算过的 KV 缓存起来，下次相同前缀的请求直接复用，省掉重复 prefill。→ 见 **Demo 3**
2. **PD 分离（Prefill/Decode Disaggregation）**：让 prefill 实例和 decode 实例分开部署，prefill 算好的 KV 通过传输引擎搬给 decode 实例。

---

## 二、本机环境的两个重要事实（务必了解）

1. **本机没有 RDMA(InfiniBand) 网卡**，所以所有传输统一用 **TCP** 协议（`MOONCAKE_PROTOCOL=tcp`）。
   在有 RDMA 的机器上把它改成 `rdma` 即可获得零拷贝、超高带宽。
2. **本机是多人共享的**：卡 5/6/7 上有别人的训练任务，所以我们 **只用卡 0/1/2/3**。

---

## 三、目录结构与学习路径

建议按 `01 → 02 → 03` 的顺序学习，每个目录的 `.py` 文件都写了详细中文注释，**强烈建议先读代码再运行**。

```
/home/mooncake/
├── env.sh                       # 公共环境变量（先 source 它）
├── common/
│   ├── start_master.sh          # 启动 master + metadata 服务（Store 的“大脑”）
│   └── stop_master.sh           # 停止它们
├── 01_store_basics/             # 【第 1 课】Store 入门：单进程 put/get/remove
│   ├── store_basics.py
│   └── run.sh                   # 一键运行
├── 02_store_cross_process/      # 【第 2 课】Store 跨进程：生产者写 / 消费者读 + 零拷贝
│   ├── _common.py
│   ├── producer.py
│   ├── consumer.py
│   └── run.sh
└── 03_sglang_hicache/           # 【第 3 课】真实集成：Mooncake 作为 SGLang 的 L3 KV 缓存
    ├── start_server.sh          # 4 卡(TP=4) 启动 SGLang，L3 后端=mooncake
    └── send_request.sh          # 发请求观察缓存命中
```

---

## 四、快速开始

```bash
conda activate <你的环境名>   # 先激活装好 sglang+mooncake 的 conda 环境
cd /home/mooncake

# 第 1 课：Store 入门（会自动拉起 master）
bash 01_store_basics/run.sh

# 第 2 课：跨进程生产者-消费者
bash 02_store_cross_process/run.sh

# 第 3 课：SGLang + Mooncake L3 缓存
#   终端A：
bash 03_sglang_hicache/start_server.sh
#   等到日志出现 "The server is fired up" 后，另开终端B：
bash 03_sglang_hicache/send_request.sh

# 全部玩完后，停掉后台的 master：
bash common/stop_master.sh
```

> 提示：`01` 和 `02` 的 `run.sh` 会自动调用 `common/start_master.sh`；master 一旦启动会一直在后台运行，多个 demo 可共用，不必重复启动。

---

## 五、每一课讲了什么

### 第 1 课 `01_store_basics`：把 Store 当分布式字典
- 学会 `setup / put / is_exist / get / remove / close` 这套最基本的 API。
- 理解三个角色：本进程是 **client**，它连 **master**，并贡献一块 **segment** 内存。
- 理解 **租约(lease)**：刚写入的对象会被保护一小段时间，期间不能删（demo 里会演示如何处理）。

### 第 2 课 `02_store_cross_process`：跨进程共享才是重点
- `producer.py` 和 `consumer.py` 是 **两个独立进程**，连同一个 master，因此看到同一个 KV 仓库。
- 关键认知：**数据存放在贡献内存的那个进程里**，所以 producer 必须保持在线，consumer 才能读到 —— 这正是 PD 分离的雏形。
- 演示 `put_tensor / get_tensor`（直接存取 PyTorch 张量）与 **零拷贝** 的 `register_buffer + get_into`（数据直接落进你预留的内存，不额外拷贝）。

### 第 3 课 `03_sglang_hicache`：真实推理场景
- SGLang 的分级 KV 缓存：**L1=GPU 显存 → L2=主机 DRAM → L3=Mooncake Store**。
- 用 4 张卡张量并行(TP=4) 起一个 Llama-3.1-8B 服务，指定 `--hicache-storage-backend mooncake`。
- 发两次共享长前缀的请求，第 2 次能复用缓存（乃至从 L3 Mooncake 取回 KV），省去重复 prefill。
- 首次启动时 SGLang 会捕获 CUDA Graph，在本机上可能较慢；想快速体验可：
  `SGLANG_EXTRA_ARGS="--disable-cuda-graph" bash 03_sglang_hicache/start_server.sh`

---

## 六、关于底层 Transfer Engine 的说明

Store 的高层 `put/get` 底层正是靠 **Transfer Engine** 搬数据。SGLang 里对它的封装可参考其源码中的：
`sglang/srt/distributed/device_communicators/mooncake_transfer_engine.py`

> 注意：直接裸用 `mooncake.engine.TransferEngine` 在 **本机这种“无 RDMA、但有 NVLink”的环境** 下，
> 对“主机内存点对点传输”支持不佳（引擎会自动选用只支持 GPU 显存的 NVLink 传输通道）。
> 因此本 demo 选择从更稳、更常用的 **Store API** 入手 —— 这也是 SGLang 实际使用 Mooncake 的主要方式。
> 在有 RDMA 网卡的机器上，裸用 Transfer Engine（`P2PHANDSHAKE` 模式）做主机内存点对点传输是完全可行的。

---

## 七、常见问题排查

- **`setup 失败 / 连不上`**：master 没起来。先 `bash common/start_master.sh`，日志在 `/tmp/mooncake_master.log`。
- **`remove` 返回负数（如 -706）**：对象租约未过期。等一会再删，或用 `store.remove(key, force=True)`。
- **端口被占用**：默认 master=50051、metadata=8080。可在 `env.sh` 里改。
- **SGLang 启动很久没就绪**：多半在捕获 CUDA Graph，耐心等 `The server is fired up`；或加 `--disable-cuda-graph`。
- **查看 Store 实时状态**：`tail -f /tmp/mooncake_master.log`（含 Keys 数量、各类请求计数等）。
```
