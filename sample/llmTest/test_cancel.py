"""LLM 取消机制使用示例 —— 演示 StreamAsync / InvokeAsync 的 CancellationToken 用法。

示例覆盖:
  1. 流式调用中途取消 —— 收到若干 chunk 后取消，验证快速终止
  2. 调用前取消检测 —— 验证立即返回，不发起 HTTP 请求
  3. 并发流式取消 —— 多个 StreamAsync 同时取消，验证无死锁
"""

import asyncio
import sys
import os
import time

# 将项目根目录加入 sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from llm import LLMManager, ChatMessage, CancellationToken, LLMError


# ─── 示例 1: 流式调用中途取消 ────────────────────────────────────────

async def example_stream_cancel():
    """收到若干 chunk 后手动取消，验证流快速终止。"""
    print("─" * 40)
    print("[示例1] StreamAsync 中途取消")

    client = LLMManager.GetClient("deepseek-mid")
    token = CancellationToken()
    chunkCount = 0

    t0 = time.monotonic()
    try:
        async for _chunk in client.StreamAsync(
            [ChatMessage.User("请写一篇500字关于AI未来的文章。")],
            temperature=0.7, maxTokens=4096, cancellationToken=token,
        ):
            chunkCount += 1
            if chunkCount >= 3:
                token.Cancel()  # 拿到3个chunk后取消
    except LLMError:
        pass

    elapsed = time.monotonic() - t0
    print(f"  收到 {chunkCount} 个 chunk 后取消，耗时 {elapsed:.2f}s")
    assert chunkCount <= 10, f"取消后应快速终止，实际收到 {chunkCount} chunks"
    print("  ✓ 通过")


# ─── 示例 2: 调用前取消检测 ──────────────────────────────────────────

async def example_invoke_cancel_before():
    """提前 Cancel，验证 InvokeAsync 立即抛出 LLMError 而不发起网络请求。"""
    print("─" * 40)
    print("[示例2] InvokeAsync 调用前取消")

    client = LLMManager.GetClient("deepseek-mid")
    token = CancellationToken()
    token.Cancel()  # 提前取消

    t0 = time.monotonic()
    try:
        await client.InvokeAsync([ChatMessage.User("Hello")], cancellationToken=token)
    except LLMError as e:
        elapsed = time.monotonic() - t0
        print(f"  立即抛出 LLMError，耗时 {elapsed:.3f}s (未发起网络请求)")
        assert elapsed < 1.0, f"应极速返回: {elapsed:.3f}s"
        print("  ✓ 通过")


# ─── 示例 3: 并发流式取消 ────────────────────────────────────────────

async def example_concurrent_cancel():
    """多个 StreamAsync 同时取消，验证无死锁、无连接泄漏。"""
    print("─" * 40)
    print("[示例3] 并发 StreamAsync 同时取消")

    client = LLMManager.GetClient("deepseek-mid")

    async def doStream(_idx: int) -> int:
        token = CancellationToken()
        cnt = 0
        try:
            async for _chunk in client.StreamAsync(
                [ChatMessage.User("写一首诗")],
                maxTokens=2048, cancellationToken=token,
            ):
                cnt += 1
                if cnt >= 2:
                    token.Cancel()
        except Exception:
            pass
        return cnt

    tasks = [asyncio.create_task(doStream(i)) for i in range(3)]
    results = await asyncio.gather(*tasks)
    print(f"  各任务 chunk 数: {results}")
    assert all(r <= 8 for r in results), f"并发取消应快速终止: {results}"
    print("  ✓ 通过")


# ─── 主入口 ─────────────────────────────────────────────────────────

async def main():
    print("LLM 取消机制 — 使用示例")
    print("=" * 40)

    await example_stream_cancel()
    await example_invoke_cancel_before()
    await example_concurrent_cancel()

    await LLMManager.CloseAsync()

    print("=" * 40)
    print("全部示例完成 ✓")


if __name__ == "__main__":
    asyncio.run(main())
