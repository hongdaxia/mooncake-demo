#!/usr/bin/env bash
# ============================================================================
# Demo 3 配套：向 SGLang server 发请求，观察 Mooncake L3 缓存是否命中
# ----------------------------------------------------------------------------
# 玩法：
#   我们发两次“共享同一段长前缀”的请求。
#   - 第 1 次：前缀 KV 需要现算(prefill)，算完后会逐级写入 L2(DRAM)/L3(Mooncake)。
#   - 第 2 次：相同前缀的 KV 可以从缓存(乃至 L3 Mooncake)取回，省去重复计算，
#             表现为更短的首字延迟 / 更高的 cached tokens。
#
# 观察方法：发完请求后，去看 server 端日志 /tmp/sglang_hicache_server.log，
#           搜索 "cached" / "hit" / "prefix" 相关字样，能看到缓存命中 token 数变化。
# ============================================================================
set -euo pipefail
PORT="${SGLANG_PORT:-30000}"
BASE="http://127.0.0.1:${PORT}"

# 一段较长的共享前缀（故意写长一点，便于产生可缓存的 KV）。
PREFIX="你是一位资深的分布式系统专家。请基于以下背景作答：Mooncake 是一个以 KVCache 为中心的大模型推理架构，"\
"它通过把 KVCache 从 GPU 显存下沉到 DRAM 乃至外部存储，实现前缀复用与 PD 分离。现在请回答："

ask () {
    local q="$1"
    curl -s "${BASE}/generate" \
        -H "Content-Type: application/json" \
        -d "{\"text\": \"${PREFIX}${q}\", \"sampling_params\": {\"max_new_tokens\": 32, \"temperature\": 0}}"
    echo
}

echo "================ 检查 server 是否就绪 ================"
if ! curl -s "${BASE}/health" >/dev/null 2>&1; then
    echo "server 还没就绪（${BASE}）。请先运行 start_server.sh 并等待加载完成。"
    exit 1
fi
echo "server 就绪。"

echo
echo "================ 第 1 次请求（前缀 KV 需要现算）================"
time ask "请用一句话概括 Mooncake 的核心思想。"

echo
echo "================ 第 2 次请求（相同前缀，应命中缓存）================"
time ask "请再用一句话说明它对推理吞吐的帮助。"

echo
echo "提示：对比两次的耗时；并查看 server 日志里的缓存命中统计："
echo "  grep -iE 'cache|hit|prefix|token usage' /tmp/sglang_hicache_server.log | tail -20"
