#!/usr/bin/env bash
# ============================================================================
# 启动 Mooncake Store 的“大脑”：master 服务 + HTTP metadata 服务
# ----------------------------------------------------------------------------
# Mooncake Store 由三类角色组成，本脚本把后两个服务端用一个进程拉起来：
#
#   1) Client（客户端）—— 就是我们 demo 里的 Python 进程，负责 put/get 数据，
#      并贡献/使用一块内存(segment)。它运行在每个业务进程里。
#   2) Master（主节点）—— 全局“目录服务/调度器”：记录每个 key 的对象存在哪台机器、
#      哪块内存里，管理副本、租约(lease)、淘汰(eviction)。本身不存大块数据。
#   3) Metadata Server（元数据服务）—— 传输引擎用它交换“谁在哪个 ip:port、
#      哪块内存可被远程访问”等连接信息。可用 etcd，也可用 Mooncake 自带的 HTTP 版。
#
# 本脚本用 master 内置的 HTTP metadata server，一条命令同时拉起 master(50051)
# 和 metadata(8080)，省去单独再起一个 etcd/metadata 进程。
# ============================================================================
set -euo pipefail

# 加载公共环境变量（端口、协议等）。
source "$(dirname "$(readlink -f "$0")")/../env.sh" >/dev/null 2>&1 || source /home/mooncake/env.sh

MASTER_BIN="/usr/local/bin/mooncake_master"
RPC_PORT="${MOONCAKE_MASTER_ADDR##*:}"          # 从 127.0.0.1:50051 里取出 50051
META_PORT="${MOONCAKE_METADATA_PORT:-8080}"
LOG_FILE="/tmp/mooncake_master.log"

# 如果已经在跑，就不重复启动。
if pgrep -f "mooncake_master --port ${RPC_PORT}" >/dev/null 2>&1; then
    echo "[start_master] master 已经在运行 (端口 ${RPC_PORT})，无需重复启动。"
    exit 0
fi

echo "[start_master] 启动 master(rpc=${RPC_PORT}) + metadata(http=${META_PORT}) ..."
# 关键参数说明：
#   --port                          master RPC 端口（客户端连这个端口找对象）
#   --enable_http_metadata_server   顺带启动 HTTP metadata 服务
#   --http_metadata_server_port     metadata 服务端口
#   --default_kv_lease_ttl          每个对象写入后的“租约”毫秒数，租约内不可被淘汰/删除。
#                                   设小一点(1000ms)方便 demo 里演示 remove。
nohup "${MASTER_BIN}" \
    --port "${RPC_PORT}" \
    --enable_http_metadata_server \
    --http_metadata_server_port "${META_PORT}" \
    --default_kv_lease_ttl 1000 \
    > "${LOG_FILE}" 2>&1 &

# 等待端口就绪。
for i in $(seq 1 20); do
    if curl -s -o /dev/null "http://127.0.0.1:${META_PORT}/metadata?key=probe" 2>/dev/null; then
        echo "[start_master] 启动成功！"
        echo "  - master 地址   : ${MOONCAKE_MASTER_ADDR}"
        echo "  - metadata 地址 : ${MOONCAKE_METADATA_SERVER}"
        echo "  - 日志文件      : ${LOG_FILE}"
        exit 0
    fi
    sleep 0.5
done

echo "[start_master] 启动超时，请查看日志：${LOG_FILE}"
exit 1
