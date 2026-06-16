#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================================
Demo 1：Mooncake Store 入门 —— 把它当成一个“分布式 KV 对象仓库”
----------------------------------------------------------------------------
【先建立直觉】
  Mooncake Store 就像一个 *分布式的大字典*：
      store.put("某个key", b"一坨字节")     # 写
      data = store.get("某个key")            # 读
  和 Redis 很像，但它的设计目标是“在 GPU 推理集群里高速搬运 KVCache”，
  所以底层用 RDMA/TCP 零拷贝传输，数据直接落在各节点贡献出来的内存池里。

【三个角色（运行前请先启动 master，见同目录 run.sh / ../common/start_master.sh）】
  - master         : 全局目录，记录“哪个 key 的数据在哪块内存”，管理副本与淘汰。
  - metadata server: 传输引擎用它交换各节点的网络连接信息。
  - client(本进程) : 调 setup() 后，本进程会：
        1) 向 master 注册自己；
        2) 贡献一块 “global segment” 内存(本 demo 256MB)，作为集群共享存储空间；
        3) 申请一块 “local buffer” 内存(本 demo 16MB)，作为本地收发数据的中转区。

【本 demo 演示的操作】
  setup  -> put -> is_exist -> get -> (等租约过期) remove -> 验证已删除 -> close
============================================================================
"""

import os
import time

from mooncake.store import MooncakeDistributedStore


def build_config() -> dict:
    """从环境变量(env.sh 里设置)拼出 Store 的配置字典。"""
    return {
        # 本机标识。单机用回环地址即可；多机时填本机真实 IP。
        "local_hostname": os.environ.get("MOONCAKE_LOCAL_HOSTNAME", "127.0.0.1"),
        # metadata 服务地址（传输引擎用来交换连接信息）。
        "metadata_server": os.environ.get(
            "MOONCAKE_METADATA_SERVER", "http://127.0.0.1:8080/metadata"
        ),
        # 本进程贡献给“集群共享内存池”的大小。所有 put 进来的对象就放在这种 segment 里。
        "global_segment_size": 256 * 1024 * 1024,  # 256 MB
        # 本地中转缓冲区大小：get/put 时数据要先经过这块本地内存。
        "local_buffer_size": 16 * 1024 * 1024,  # 16 MB
        # 传输协议。本机无 RDMA，用 tcp。（有 RDMA 的机器填 "rdma" 性能更好）
        "protocol": os.environ.get("MOONCAKE_PROTOCOL", "tcp"),
        # RDMA 网卡列表，tcp 模式留空。
        "rdma_devices": os.environ.get("MOONCAKE_DEVICE", ""),
        # master 服务地址（客户端连它来定位对象）。
        "master_server_addr": os.environ.get("MOONCAKE_MASTER_ADDR", "127.0.0.1:50051"),
    }


def main():
    store = MooncakeDistributedStore()

    cfg = build_config()
    print("[demo] 即将用以下配置连接 Mooncake Store：")
    for k, v in cfg.items():
        print(f"        {k:20s} = {v}")

    # ---- 1. setup：连接 master、注册自己、挂载共享内存 segment ----
    # 返回 0 表示成功。这一步会打印一堆 C++ 日志(I.../W...)，属于正常现象。
    ret = store.setup(cfg)
    assert ret == 0, f"setup 失败, ret={ret}（master 起来了吗？）"
    print("\n[demo] ✅ setup 成功，已连接 Mooncake Store。\n")

    key = "lesson1/hello"
    value = "你好 Mooncake！这是我存进分布式 KV 仓库的第一条数据。".encode("utf-8")

    # ---- 2. put：写入一个对象 ----
    # put(key, value)；返回 0 表示成功。value 接收 bytes / 可读 buffer。
    ret = store.put(key, value)
    assert ret == 0, f"put 失败, ret={ret}"
    print(f"[demo] 已写入 key='{key}'，{len(value)} 字节。")

    # ---- 3. is_exist：查询某个 key 是否存在（返回 1 存在 / 0 不存在）----
    print(f"[demo] is_exist('{key}') = {store.is_exist(key)}  (1=存在)")

    # ---- 4. get：读回对象 ----
    # get(key) 返回 bytes。底层会把数据从存放它的 segment 经传输引擎搬到本地。
    got = store.get(key)
    print(f"[demo] 读回 {len(got)} 字节，内容 = {got.decode('utf-8')!r}")
    assert got == value, "读回的数据和写入的不一致！"
    print("[demo] ✅ 读回的数据与写入完全一致。\n")

    # ---- 5. remove：删除对象 ----
    # 注意“租约(lease)”机制：对象写入后，在 default_kv_lease_ttl 毫秒内受保护，
    # 直接 remove 会返回错误码(如 -706)。我们在 start_master.sh 里把租约设成了 1000ms，
    # 这里等 1.2 秒让租约过期再删（也可以用 store.remove(key, force=True) 强制删）。
    print("[demo] 等待对象租约(lease)过期后再删除 ...")
    time.sleep(1.2)
    ret = store.remove(key)
    if ret != 0:
        print(f"[demo] 普通 remove 返回 {ret}（可能租约未过期），改用 force=True 强删。")
        ret = store.remove(key, force=True)
    print(f"[demo] remove('{key}') = {ret} (0=成功)")
    print(f"[demo] 删除后 is_exist('{key}') = {store.is_exist(key)}  (0=已不存在)")

    # ---- 6. close：断开连接，归还内存 ----
    store.close()
    print("\n[demo] ✅ 全流程结束，已关闭 Store 连接。")


if __name__ == "__main__":
    main()
