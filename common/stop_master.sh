#!/usr/bin/env bash
# ============================================================================
# 停止 Mooncake master / metadata 服务
# ============================================================================
echo "[stop_master] 正在停止 mooncake_master ..."
# 用 pgrep 找到 master 进程并结束。这里特意匹配带 --port 的命令行，
# 避免误杀其它无关进程。
pids=$(pgrep -f "mooncake_master --port" || true)
if [ -z "${pids}" ]; then
    echo "[stop_master] 没有发现正在运行的 master。"
    exit 0
fi
echo "${pids}" | xargs -r kill
sleep 1
echo "[stop_master] 已停止 (pids: ${pids})。"
