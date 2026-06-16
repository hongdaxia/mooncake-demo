#!/usr/bin/env bash
# ============================================================================
# Demo 3：把 Mooncake Store 当成 SGLang 的“三级 KV 缓存(L3)”后端
# ----------------------------------------------------------------------------
# 【SGLang 的分级 KV 缓存(HiCache)】
#   L1 = GPU 显存里的 KVCache（最快，最贵，最小）
#   L2 = 主机 DRAM 里的 KVCache（host memory pool）
#   L3 = 外部存储后端 —— 这里就用 Mooncake Store！（可跨进程/跨机共享、容量大）
#
#   当一个请求的前缀(prefix)KV 在 GPU/DRAM 里被淘汰后，可以落到 L3(Mooncake)；
#   下次再来相同前缀的请求，就能从 Mooncake 把 KV 取回来，省去重复 prefill 计算。
#   这就是 Mooncake 在真实推理系统里的核心用途之一。
#
# 【本脚本做的事】
#   1) 启动 Mooncake master + metadata（复用 ../common/start_master.sh）。
#   2) 用 4 张 GPU(张量并行 TP=4) 启动 SGLang server，加载 Llama-3.1-8B，
#      并开启分级缓存、指定 L3 后端为 mooncake。
#
# 运行：  bash start_server.sh
# 就绪后另开一个终端运行：  bash send_request.sh
# ============================================================================
set -euo pipefail
HERE="$(dirname "$(readlink -f "$0")")"
source "${HERE}/../env.sh"

# 1) 先把 Mooncake 的 master/metadata 拉起来。
bash "${HERE}/../common/start_master.sh"

# 2) 通过环境变量告诉 SGLang 的 mooncake 后端怎么连。
#    （SGLang 的 MooncakeStore 会从这些环境变量里读取配置）
export MOONCAKE_MASTER="${MOONCAKE_MASTER_ADDR}"             # master 地址
export MOONCAKE_PROTOCOL="${MOONCAKE_PROTOCOL}"             # tcp
export MOONCAKE_DEVICE="${MOONCAKE_DEVICE}"                 # 网卡名(tcp 留空)
export MOONCAKE_LOCAL_HOSTNAME="${MOONCAKE_LOCAL_HOSTNAME}" # 127.0.0.1
# metadata 用 HTTP 服务（本机无 RDMA，避免传输引擎误选 NVLink；用 http 会自动走 TCP）。
export MOONCAKE_TE_META_DATA_SERVER="${MOONCAKE_METADATA_SERVER}"
# 每个 server 进程贡献给 Mooncake 的共享内存大小（这里给 4GB 放 KV）。
export MOONCAKE_GLOBAL_SEGMENT_SIZE="4gb"

PORT="${SGLANG_PORT:-30000}"

echo
echo "================ 启动 SGLang server (TP=4, L3=mooncake) ================"
echo "  模型      : ${MODEL_PATH}"
echo "  使用 GPU  : ${CUDA_VISIBLE_DEVICES} (张量并行 TP=4)"
echo "  HTTP 端口 : ${PORT}"
echo "  L3 后端   : mooncake @ ${MOONCAKE_MASTER}"
echo "  日志      : /tmp/sglang_hicache_server.log"
echo "（首次加载模型需要一两分钟，请耐心等待 'The server is fired up' 字样）"
echo

# 关键参数：
#   --tp-size 4                       张量并行，用满 4 张卡
#   --enable-hierarchical-cache       打开 L1/L2/L3 分级 KV 缓存
#   --hicache-storage-backend mooncake  指定 L3 后端为 Mooncake Store
#   --hicache-ratio 2                 L2(host) 容量设为 L1(device) 的 2 倍
#   --page-size 64                    每页 token 数（HiCache 以页为单位换入换出）
#
# 小贴士：本机首次启动时，SGLang 会逐个 batch size 捕获 CUDA Graph，
#   在某些新硬件上可能要等十几分钟。想快速体验可以临时关掉 CUDA Graph：
#       SGLANG_EXTRA_ARGS="--disable-cuda-graph" bash start_server.sh
#   （生产环境建议保留 CUDA Graph 以获得更高解码吞吐）
python -m sglang.launch_server \
    --model-path "${MODEL_PATH}" \
    --tp-size 4 \
    --host 127.0.0.1 \
    --port "${PORT}" \
    --page-size 64 \
    --enable-hierarchical-cache \
    --hicache-ratio 2 \
    --hicache-storage-backend mooncake \
    ${SGLANG_EXTRA_ARGS:-} \
    2>&1 | tee /tmp/sglang_hicache_server.log
