# ============================================================================
# Mooncake 学习 Demo —— 公共环境变量
# ----------------------------------------------------------------------------
# 用法：在运行任何 demo 脚本前先 `source` 本文件，让所有终端共享同一套配置。
#       source /home/mooncake/env.sh
#
# 设计说明（务必先读）：
#   1) 我们约定只使用本机的前 4 张 GPU（卡 0/1/2/3），通过 CUDA_VISIBLE_DEVICES 限制。
#   2) 本机没有 RDMA(InfiniBand) 网卡，因此 Mooncake 的传输协议统一用 "tcp"，
#      device_name 留空即可（RDMA 场景才需要填 mlx5_0 之类的网卡名）。
#   3) 单机演示，hostname 一律用 127.0.0.1（回环地址），多机时换成真实 IP。
# ============================================================================

# ---- conda 环境 ----
# 运行前请先自行激活已安装好 sglang 和 mooncake 的 conda 环境，例如：
#     conda activate <你的环境名>
# 本脚本不替你激活环境，只负责设置后续 demo 所需的变量。

# ---- 只用前 4 张卡 ----
# 这一行非常关键：它让进程只能看到物理卡 0~3，逻辑编号会被重映射为 0~3。
export CUDA_VISIBLE_DEVICES="0,1,2,3"

# ---- 模型路径 ----
export MODEL_PATH="/home/Llama-3.1-8B-Instruct"

# ---- Mooncake 传输相关 ----
# 传输协议：本机无 RDMA，使用 tcp。（有 RDMA 的机器可改为 rdma 获得零拷贝高带宽）
export MOONCAKE_PROTOCOL="tcp"
# RDMA 网卡名；tcp 模式下留空。
export MOONCAKE_DEVICE=""
# 本机主机名 / IP，单机回环即可。
export MOONCAKE_LOCAL_HOSTNAME="127.0.0.1"

# ---- Mooncake Store 的两个服务端口 ----
# master 服务：负责对象元数据、副本/淘汰管理（类似“目录服务”）。
export MOONCAKE_MASTER_ADDR="127.0.0.1:50051"
# HTTP metadata 服务：传输引擎用它来交换各节点的连接信息（也可用 etcd 代替）。
# 这里用 master 内置的 http metadata server，监听 8080。
export MOONCAKE_METADATA_PORT="8080"
export MOONCAKE_METADATA_SERVER="http://127.0.0.1:8080/metadata"

echo "[env.sh] Mooncake demo 环境已加载："
echo "  当前 conda 环境      = ${CONDA_DEFAULT_ENV:-未检测到(请确认已激活)}"
echo "  CUDA_VISIBLE_DEVICES= ${CUDA_VISIBLE_DEVICES}"
echo "  MODEL_PATH          = ${MODEL_PATH}"
echo "  协议/网卡            = ${MOONCAKE_PROTOCOL} / '${MOONCAKE_DEVICE}'"
echo "  master 地址          = ${MOONCAKE_MASTER_ADDR}"
echo "  metadata 地址        = ${MOONCAKE_METADATA_SERVER}"
