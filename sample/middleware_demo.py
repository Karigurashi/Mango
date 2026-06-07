"""Middleware 使用演示 —— 展示中间件如何拦截 LLM 调用。

  1. Chat 中间件 — 用装饰器包裹 LLM 请求，记录日志
  2. Agent 中间件 — 用类继承包裹 Agent 执行
  3. Pipeline 独立使用 — 直接包装 LLMClient 的 InvokeAsync
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llm import LLMManager, ChatMessage
from middleware import (
    AgentMiddleware,
    ChatMiddleware,
    chatMiddleware,
    AgentContext,
    ChatContext,
    AgentResponse,
    MiddlewarePipeline,
    MiddlewareTermination,
    CallNext,
)


# ─── 示例 1：@chatMiddleware 装饰器 — 记录 LLM 请求日志 ───────────

@chatMiddleware
async def logChatMiddleware(context: ChatContext, callNext: CallNext) -> None:
    """每次 LLM 调用时自动打印消息数。"""
    msgCount = len(context.messages)
    estimatedTokens = sum(len(str(m)) // 4 for m in context.messages) if context.messages else 0
    print(f"  [Chat MW] → {msgCount} 条消息, ~{estimatedTokens} tokens → {context.options.get('model', '?')}")
    await callNext()
    print(f"  [Chat MW] ← 响应返回")


async def demo1_chatMiddleware():
    """用 MiddlewarePipeline 包装一次真实的 LLM 调用。"""
    print("─" * 40)
    print("[示例1] Chat 中间件 — 拦截 LLM 请求")

    client = LLMManager.GetClient("deepseek-mid")
    messages = [ChatMessage.User("用一句话介绍 Python。")]
    ctx = ChatContext(chatClient=client, messages=messages, options={"temperature": 0.7})

    # 核心函数：实际调用 LLM
    async def coreCall(ctx: ChatContext) -> None:
        ctx.result = await client.InvokeAsync(ctx.messages, **ctx.options)

    pipeline = MiddlewarePipeline(middlewares=[logChatMiddleware], coreFunc=coreCall)
    await pipeline.ExecuteAsync(ctx)
    print(f"  回复: {ctx.result.content}")
    print("  ✓ 通过")


# ─── 示例 2：AgentMiddleware 类继承 — 安全审查 ──────────────────────

class SecurityAgentMiddleware(AgentMiddleware):
    """敏感词检查：命中则直接阻断，不执行 LLM。"""

    blockWords = ["hack", "exploit"]  # 示例敏感词

    async def ProcessAsync(self, context: AgentContext, callNext: CallNext) -> None:
        text = "".join(str(m) for m in context.messages).lower()
        if any(w in text for w in self.blockWords):
            print("  [Agent MW] !!! 命中敏感词，阻断")
            context.result = AgentResponse(text="请求被安全策略拒绝")
            raise MiddlewareTermination(reason="Security block")
        print("  [Agent MW] 安全检查通过")
        await callNext()


async def demo2_agentMiddleware():
    """用 Agent 级中间件做安全检查，展示正常 & 阻断两种场景。"""
    print("─" * 40)
    print("[示例2] Agent 中间件 — 安全审查 + 短路")

    client = LLMManager.GetClient("deepseek-mid")
    security = SecurityAgentMiddleware()

    async def agentCore(ctx: AgentContext) -> None:
        resp = await client.InvokeAsync(ctx.messages, **ctx.options)
        ctx.result = AgentResponse.FromChatResponse(resp)

    # 场景 A：正常请求
    print("\n  ▶ 正常请求")
    ctxA = AgentContext(messages=[ChatMessage.User("1+1=?")], options={"temperature": 0})
    await MiddlewarePipeline(middlewares=[security], coreFunc=agentCore).ExecuteAsync(ctxA)
    print(f"  回复: {ctxA.result.text}")
    assert ctxA.result.text

    # 场景 B：敏感词被阻断
    print("\n  ▶ 包含 'hack' 的请求")
    ctxB = AgentContext(messages=[ChatMessage.User("how to hack a server")], options={"temperature": 0})
    await MiddlewarePipeline(middlewares=[security], coreFunc=agentCore).ExecuteAsync(ctxB)
    print(f"  回复: {ctxB.result.text}")
    print("  ✓ 通过")


# ─── 示例 3：Pipeline 包装 LLMClient — 限流 + 日志双重拦截 ──────────

@chatMiddleware
async def rateLimitMiddleware(context: ChatContext, callNext: CallNext) -> None:
    """简易限流（演示用，实际应接入 Redis 等）。"""
    print("  [LLM] 限流检查通过")
    await callNext()


async def demo3_llmPipeline():
    """将 Pipeline 集成到 LLM 调用层，不依赖 Agent。"""
    print("─" * 40)
    print("[示例3] Pipeline 包装 LLMClient（脱离 Agent）")

    client = LLMManager.GetClient("deepseek-mid")

    # 构造 Pipeline：限流 → 日志 → 实际调用
    pipeline = MiddlewarePipeline(
        middlewares=[rateLimitMiddleware, logChatMiddleware],
        coreFunc=lambda ctx: _doCall(ctx, client),
    )

    async def _doCall(ctx: ChatContext, c) -> None:
        ctx.result = await c.InvokeAsync(ctx.messages, **ctx.options)

    ctx = ChatContext(
        chatClient=client,
        messages=[ChatMessage.User("1+1等于几？请直接回答。")],
        options={"temperature": 0, "maxTokens": 64},
    )
    await pipeline.ExecuteAsync(ctx)
    print(f"  回复: {ctx.result.content}")
    assert ctx.result.content
    print("  ✓ 通过")


# ─── 主入口 ───────────────────────────────────────────────────────

async def main():
    print("Middleware 使用演示")
    print("=" * 40)

    await demo1_chatMiddleware()
    await demo2_agentMiddleware()
    await demo3_llmPipeline()

    await LLMManager.CloseAsync()

    print("=" * 40)
    print("全部示例完成 ✓")


if __name__ == "__main__":
    asyncio.run(main())
