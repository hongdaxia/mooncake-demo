#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================================
Demo 2 / 消费者(Consumer)：跨进程读取 producer 写入的数据
----------------------------------------------------------------------------
请在 producer.py 已经运行(并打印“数据已就绪”)之后再运行本脚本。

本脚本演示两种读取方式：
  1) 普通读：store.get / store.get_tensor —— 简单，库帮你分配内存并返回。
  2) 零拷贝读：store.get_into —— 把数据直接写进“你事先准备并注册好的内存”，
     不额外分配/拷贝。这正是高性能推理里搬运 KVCache 的方式。
============================================================================
"""

import ctypes
import time

import numpy as np
import torch

from _common import KEY_BYTES, KEY_TENSOR, DONE_KEY, connect_store


def main():
    store = connect_store(global_segment_mb=128)
    print("[consumer] ✅ 已连接 Store（与 producer 连的是同一个 master）。")

    # 等待 producer 把数据准备好（key 出现）。
    print("[consumer] 等待 producer 写入数据 ...")
    for _ in range(120):
        if store.is_exist(KEY_TENSOR):
            break
        time.sleep(0.5)
    assert store.is_exist(KEY_TENSOR), "等不到 producer 的数据，请先运行 producer.py"

    # ---- 读取方式 1：普通 get（bytes）----
    raw = store.get(KEY_BYTES)
    print(f"\n[consumer] get bytes  key='{KEY_BYTES}' -> {len(raw)} 字节")
    print(f"[consumer]   内容 = {raw.decode('utf-8')!r}")

    # ---- 读取方式 1：普通 get_tensor（PyTorch 张量）----
    tensor = store.get_tensor(KEY_TENSOR)
    print(f"[consumer] get_tensor key='{KEY_TENSOR}' -> shape={tuple(tensor.shape)} dtype={tensor.dtype}")
    print(f"[consumer]   tensor 求和(应与 producer 一致) = {tensor.sum().item()}")

    # ---- 读取方式 2：零拷贝 get_into ----
    # 思路：先查对象大小 -> 准备一块同样大的 numpy 缓冲区 -> 把它注册给 Store ->
    #       调 get_into 让数据“直接落进”这块缓冲区（不经过额外的 Python bytes 拷贝）。
    size = store.get_size(KEY_BYTES)
    print(f"\n[consumer] 演示零拷贝读取：对象大小 = {size} 字节")
    buf = np.zeros(size, dtype=np.uint8)               # 预先分配好的接收缓冲区
    buf_ptr = buf.ctypes.data_as(ctypes.c_void_p).value  # 拿到这块内存的地址(整数)
    assert store.register_buffer(buf_ptr, size) == 0     # 把缓冲区注册给 Store
    ret = store.get_into(KEY_BYTES, buf_ptr, size)       # 直接读入；返回读到的字节数
    print(f"[consumer]   get_into 返回 {ret} (读入的字节数)")
    print(f"[consumer]   零拷贝读到的内容 = {bytes(buf[:ret]).decode('utf-8')!r}")
    store.unregister_buffer(buf_ptr)  # 用完注销缓冲区

    # ---- 告诉 producer：我读完了，你可以退出了 ----
    store.put(DONE_KEY, b"1")
    print("\n[consumer] ✅ 读取并校验完成，已通知 producer 退出。")
    store.close()


if __name__ == "__main__":
    main()
