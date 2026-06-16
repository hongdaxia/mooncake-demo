#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================================
Demo 2 / 生产者(Producer)：写入数据，并保持在线供消费者读取
----------------------------------------------------------------------------
运行顺序：先启动 master，再开一个终端运行本脚本，最后在第三个终端运行 consumer.py。
（用 run.sh 可以自动按顺序拉起。）

【关键认知】
  Mooncake Store 的对象数据，物理上存放在“贡献了内存的客户端进程”的 segment 里。
  也就是说：本 producer 进程贡献了 256MB segment，put 进去的数据就躺在它的内存里。
  ❗因此 producer 必须保持运行，consumer 才能读到数据；
    producer 一旦退出，它贡献的内存被回收，数据也就没了。
  这模拟了真实的 PD 分离：prefill 实例把算好的 KVCache 放在自己显存里，
  decode 实例再跨进程/跨机把它取走。
============================================================================
"""

import time

import torch

from _common import KEY_BYTES, KEY_TENSOR, DONE_KEY, connect_store


def main():
    store = connect_store(global_segment_mb=256)
    print("[producer] ✅ 已连接 Store，本进程贡献了 256MB 共享内存。")

    # ---- 写入 1：一段普通字节 ----
    raw = ("Mooncake 生产者写入的原始字节，时间戳=" + str(time.time())).encode("utf-8")
    assert store.put(KEY_BYTES, raw) == 0
    print(f"[producer] 已写入 bytes  key='{KEY_BYTES}' ({len(raw)} 字节)")

    # ---- 写入 2：一个 PyTorch 张量（模拟一小块 KVCache）----
    # put_tensor / get_tensor 会自动处理张量的 shape/dtype 元信息，跨进程读回时能还原。
    # 这里用 CPU 张量演示最直观；换成 .cuda() 的 GPU 张量同理（SGLang 内部就是传 GPU KV）。
    tensor = torch.arange(0, 4096, dtype=torch.float32).reshape(16, 256)
    assert store.put_tensor(KEY_TENSOR, tensor) == 0
    print(f"[producer] 已写入 tensor key='{KEY_TENSOR}' shape={tuple(tensor.shape)} dtype={tensor.dtype}")
    # 记录一个校验和，方便 consumer 端对比是否一致。
    print(f"[producer] tensor 求和(校验用) = {tensor.sum().item()}")

    # ---- 保持在线，等待 consumer 读完 ----
    print("\n[producer] 数据已就绪，进程保持在线。请到另一个终端运行 consumer.py ...")
    print("[producer] （正在等待 consumer 完成，最多等 180 秒）")
    for _ in range(360):
        if store.is_exist(DONE_KEY):
            print("[producer] 检测到 consumer 已读取完成，准备退出。")
            break
        time.sleep(0.5)
    else:
        print("[producer] 等待超时，仍然退出。")

    store.close()
    print("[producer] 已关闭连接，退出。")


if __name__ == "__main__":
    main()
