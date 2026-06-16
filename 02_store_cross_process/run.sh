#!/usr/bin/env bash
# ============================================================================
# 一键运行 Demo 2：启动 master -> 后台跑 producer -> 前台跑 consumer
# 用法：  bash run.sh
#
# 想手动体会“跨进程”的感觉时，可以分三个终端自己来：
#   终端A:  bash ../common/start_master.sh
#   终端B:  python -u producer.py
#   终端C:  python -u consumer.py
# ============================================================================
set -euo pipefail
HERE="$(dirname "$(readlink -f "$0")")"
source "${HERE}/../env.sh"

bash "${HERE}/../common/start_master.sh"

echo
echo "================ 后台启动 producer ================"
python -u "${HERE}/producer.py" > /tmp/mooncake_demo2_producer.log 2>&1 &
PRODUCER_PID=$!
echo "[run] producer 已在后台启动 (pid=${PRODUCER_PID})，日志：/tmp/mooncake_demo2_producer.log"

# 给 producer 一点时间完成 setup + 写入。
sleep 5

echo
echo "================ 前台运行 consumer ================"
python -u "${HERE}/consumer.py"

echo
echo "================ producer 端日志 ================"
wait ${PRODUCER_PID} 2>/dev/null || true
grep -vE "^I[0-9]|^W[0-9]|Logging before" /tmp/mooncake_demo2_producer.log | tail -20
