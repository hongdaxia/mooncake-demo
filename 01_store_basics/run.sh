#!/usr/bin/env bash
# ============================================================================
# 一键运行 Demo 1：自动启动 master，再跑 store_basics.py
# 用法：  bash run.sh        （请先自行激活装好 sglang+mooncake 的 conda 环境）
# ============================================================================
set -euo pipefail
HERE="$(dirname "$(readlink -f "$0")")"
source "${HERE}/../env.sh"

# 1) 启动 master + metadata（若已在运行会自动跳过）。
bash "${HERE}/../common/start_master.sh"

echo
echo "================ 运行 store_basics.py ================"
# 2) 运行 demo。用 python -u 关闭缓冲，日志能实时打印。
python -u "${HERE}/store_basics.py"
