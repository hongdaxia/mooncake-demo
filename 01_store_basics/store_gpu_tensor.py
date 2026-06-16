#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================================
Demo 1 附加：把 GPU 张量存进 Mooncake Store —— 直接拷贝 vs 零拷贝
----------------------------------------------------------------------------
运行前请先启动 master：bash ../common/start_master.sh
然后：python store_gpu_tensor.py

本脚本演示两种把 GPU 张量放进 Store 的方式：
  方式 A（最简单）：put_tensor / get_tensor
      —— 一行搞定，库帮你打包 shape/dtype，但数据路径上会有额外拷贝。
  方式 B（零拷贝）：register_buffer + put_from / get_into
      —— 你把一块显存“注册”给引擎，数据直接从这块显存做 DMA 搬运，
         跳过 Python 字节对象和中转 buffer。这是推理系统搬运 KVCache 的真正方式。

【零拷贝原理一句话】
  register_buffer 把这块内存登记成一个 MR(Memory Region)，引擎之后就能对它
  做直接 DMA：
    - 有 RDMA 网卡：走单边 RDMA(配合 GPUDirect 可直读/写显存，不经过 host)；
    - 单机多卡：走 NVLink P2P；
    - 无 RDMA(本机)：回退到 cudaMemcpy + TCP，API 与概念不变，只是带宽不同。
============================================================================
"""

import os

import torch
from mooncake.store import MooncakeDistributedStore


def build_config() -> dict:
    """与 store_basics.py 相同的连接配置（从 env.sh 的环境变量读取）。"""
    return {
        "local_hostname": os.environ.get("MOONCAKE_LOCAL_HOSTNAME", "127.0.0.1"),
        "metadata_server": os.environ.get(
            "MOONCAKE_METADATA_SERVER", "http://127.0.0.1:8080/metadata"
        ),
        "global_segment_size": 256 * 1024 * 1024,
        "local_buffer_size": 32 * 1024 * 1024,
        "protocol": os.environ.get("MOONCAKE_PROTOCOL", "tcp"),
        "rdma_devices": os.environ.get("MOONCAKE_DEVICE", ""),
        "master_server_addr": os.environ.get("MOONCAKE_MASTER_ADDR", "127.0.0.1:50051"),
    }


def demo_simple(store: MooncakeDistributedStore):
    """方式 A：先把 GPU 张量搬到 CPU，再用 put_tensor / get_tensor —— 最省心。

    注意：put_tensor 只接受 CPU 张量（直接传 CUDA 张量会崩溃）。
    所以“直接拷贝”方式的本质是：GPU 显存 --cudaMemcpy--> 主机内存 --> 存进 Store。
    数据在路径上多了一次 GPU->CPU 的拷贝，但写法最简单。
    """
    print("\n" + "=" * 60)
    print("方式 A：GPU->CPU 后 put_tensor / get_tensor（直接拷贝，最简单）")
    print("=" * 60)

    # 在 GPU 上造一个张量。
    x = torch.arange(0, 1024, dtype=torch.float32, device="cuda:0") * 1.5
    print(f"[A] 源张量在 {x.device}，校验和 = {x.sum().item()}")

    # 关键：先把 GPU 张量拷到 CPU，put_tensor 只能接收 CPU 张量。
    x_cpu = x.cpu()
    assert store.put_tensor("gpu/simple", x_cpu) == 0
    print("[A] 已 GPU->CPU 拷贝，再 put_tensor 成功。")

    # get_tensor 读回的是 CPU 张量，需要时再 .cuda() 送回显存。
    y_cpu = store.get_tensor("gpu/simple")
    y = y_cpu.cuda()
    print(f"[A] 读回 CPU 张量后再送回 {y.device}，校验和 = {y.sum().item()}")
    assert torch.equal(x, y)
    print("[A] ✅ 数值一致（写法最简单，但数据多走了一趟主机内存）。")

    store.remove("gpu/simple", force=True)


def demo_zero_copy(store: MooncakeDistributedStore):
    """方式 B：register_buffer + put_from / get_into —— 零拷贝。"""
    print("\n" + "=" * 60)
    print("方式 B：register_buffer + put_from / get_into（零拷贝）")
    print("=" * 60)

    # 源：一块 GPU 显存里的张量。
    x = torch.arange(0, 1024, dtype=torch.float32, device="cuda:0") * 1.5
    nbytes = x.numel() * x.element_size()
    src_ptr = x.data_ptr()  # 这块显存的地址（一个整数）
    print(f"[B] 源张量在 {x.device}，{nbytes} 字节，校验和 = {x.sum().item()}")

    # 1) 把源显存注册给 Store（登记成 MR，之后可被直接 DMA）。
    assert store.register_buffer(src_ptr, nbytes) == 0
    print("[B] register_buffer(源) 成功。")

    # 2) 零拷贝写：直接从这块显存把数据搬进 Store，不经过 Python bytes。
    assert store.put_from("gpu/zerocopy", src_ptr, nbytes) == 0
    print("[B] put_from 成功（数据直接从显存 DMA 进 Store）。")

    # 3) 预先分配好接收用的 GPU 显存，并同样注册。
    y = torch.empty_like(x)
    dst_ptr = y.data_ptr()
    assert store.register_buffer(dst_ptr, nbytes) == 0

    # 4) 零拷贝读：数据直接落进 y 的显存，返回值是读到的字节数。
    n = store.get_into("gpu/zerocopy", dst_ptr, nbytes)
    print(f"[B] get_into 读入 {n} 字节，读回张量在 {y.device}，校验和 = {y.sum().item()}")
    assert torch.equal(x, y)  # 两个都在 cuda:0，可直接比较
    print("[B] ✅ 数值完全一致，且全程数据待在 GPU 显存里（零拷贝路径）。")

    # 5) 用完注销缓冲区、删除对象。
    store.unregister_buffer(src_ptr)
    store.unregister_buffer(dst_ptr)
    store.remove("gpu/zerocopy", force=True)


def main():
    if not torch.cuda.is_available():
        raise SystemExit("未检测到可用 GPU，本示例需要 CUDA 设备。")

    store = MooncakeDistributedStore()
    ret = store.setup(build_config())
    assert ret == 0, f"setup 失败, ret={ret}（master 起来了吗？）"
    print("✅ 已连接 Mooncake Store。")

    demo_simple(store)      # 方式 A：直接拷贝
    demo_zero_copy(store)   # 方式 B：零拷贝

    store.close()
    print("\n✅ 全部完成，已关闭连接。")


if __name__ == "__main__":
    main()
