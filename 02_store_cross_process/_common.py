# -*- coding: utf-8 -*-
"""Demo 2 公共配置：producer 和 consumer 共用同一套连接参数。"""
import os

from mooncake.store import MooncakeDistributedStore


def connect_store(global_segment_mb: int = 256) -> MooncakeDistributedStore:
    """创建并连接一个 Mooncake Store 客户端。

    注意：producer 和 consumer 是两个独立进程，但都连同一个 master，
    因此它们看到的是 *同一个* 分布式 KV 仓库 —— 这正是 Mooncake 的价值：
    把“谁生产数据”和“谁消费数据”解耦开（典型场景：prefill 节点产出 KVCache，
    decode 节点跨进程/跨机器把它取走）。
    """
    store = MooncakeDistributedStore()
    cfg = {
        "local_hostname": os.environ.get("MOONCAKE_LOCAL_HOSTNAME", "127.0.0.1"),
        "metadata_server": os.environ.get(
            "MOONCAKE_METADATA_SERVER", "http://127.0.0.1:8080/metadata"
        ),
        "global_segment_size": global_segment_mb * 1024 * 1024,
        "local_buffer_size": 32 * 1024 * 1024,
        "protocol": os.environ.get("MOONCAKE_PROTOCOL", "tcp"),
        "rdma_devices": os.environ.get("MOONCAKE_DEVICE", ""),
        "master_server_addr": os.environ.get("MOONCAKE_MASTER_ADDR", "127.0.0.1:50051"),
    }
    ret = store.setup(cfg)
    assert ret == 0, f"setup 失败, ret={ret}（master 起来了吗？）"
    return store


# 两个进程握手用的“信号 key”：consumer 读完后写它，producer 看到后才退出。
DONE_KEY = "demo2/consumer_done"

# producer 写入的几个 key。
KEY_BYTES = "demo2/raw_bytes"
KEY_TENSOR = "demo2/kv_tensor"
