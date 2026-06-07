"""LLM 调用模式示例 —— 演示 LLMClient 的四种调用方式。

  1. Invoke      — 同步非流式，返回完整 ChatResponse
  2. Stream      — 同步流式，逐块产出 ChatChunk
  3. InvokeAsync — 异步非流式，返回完整 ChatResponse
  4. StreamAsync — 异步流式，逐块产出 ChatChunk
"""

import asyncio
import sys
import os

# 将项目根目录加入 sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from llm import LLMManager, ChatMessage


# ─── 示例 1: Invoke（同步非流式）────────────────────────────────────

def example_invoke():
    """同步调用，阻塞等待完整回复，返回 ChatResponse。"""
    print("─" * 40)
    print("[示例1] Invoke 同步非流式")

    client = LLMManager.GetClient("deepseek-mid")
    resp = client.Invoke(
        [ChatMessage.User("1+1等于几？请直接回答。")],
        temperature=0.7, maxTokens=128,
    )
    print(f"  回复: {resp.content}")
    if resp.usage:
        print(f"  Token: prompt={resp.usage.promptTokens}, completion={resp.usage.completionTokens}")
    assert resp.content
    print("  ✓ 通过")


# ─── 示例 2: Stream（同步流式）─────────────────────────────────────

def example_stream():
    """同步流式调用，逐块打印增量文本，可通过 Iterator 控制节奏。"""
    print("─" * 40)
    print("[示例2] Stream 同步流式")

    client = LLMManager.GetClient("deepseek-mid")
    chunks = []
    for chunk in client.Stream(
        [ChatMessage.User("用一句话介绍Python。")],
        temperature=0.7, maxTokens=128,
    ):
        if chunk.content:
            chunks.append(chunk.content)
            print(f"  {chunk.content}", end="", flush=True)

    full = "".join(chunks)
    print(f"\n  完整回复({len(chunks)} chunks): {full}")
    assert full
    print("  ✓ 通过")


# ─── 示例 3: InvokeAsync（异步非流式）──────────────────────────────

async def example_invoke_async():
    """异步调用，不阻塞事件循环，支持 CancellationToken 取消。"""
    print("─" * 40)
    print("[示例3] InvokeAsync 异步非流式")

    client = LLMManager.GetClient("deepseek-mid")
    resp = await client.InvokeAsync(
        [ChatMessage.User("用一句话介绍异步编程。")],
        temperature=0.7, maxTokens=128,
    )
    print(f"  回复: {resp.content}")
    assert resp.content
    print("  ✓ 通过")


# ─── 示例 4: StreamAsync（异步流式）────────────────────────────────

async def example_stream_async():
    """异步流式调用，逐块产出，适合实时渲染到前端。"""
    print("─" * 40)
    print("[示例4] StreamAsync 异步流式")

    client = LLMManager.GetClient("deepseek-mid")
    chunks = []
    async for chunk in client.StreamAsync(
        [ChatMessage.User("用一句话介绍DeepSeek。")],
        temperature=0.7, maxTokens=128,
    ):
        if chunk.content:
            chunks.append(chunk.content)
            print(f"  {chunk.content}", end="", flush=True)

    full = "".join(chunks)
    print(f"\n  完整回复({len(chunks)} chunks): {full}")
    assert full
    print("  ✓ 通过")


# ─── 主入口 ───────────────────────────────────────────────────────

async def main():
    print("LLM 四种调用模式 — 使用示例")
    print("=" * 40)

    # 同步调用
    example_invoke()
    example_stream()

    # 异步调用
    await example_invoke_async()
    await example_stream_async()

    await LLMManager.CloseAsync()

    print("=" * 40)
    print("全部示例完成 ✓")


if __name__ == "__main__":
    asyncio.run(main())
