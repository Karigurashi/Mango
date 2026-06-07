"""程序化构建 Workflow 示例 —— 演示用代码（非 JSON）组装工作流。

所有节点通过 AddNodeAuto 自动分配 ID，无需手动编号。

示例覆盖:
  1. 线性工作流 —— 最基本的节点创建与连接
  2. 含延迟的多步骤 —— 捕获返回 ID，链式连边
  3. 复合节点 (Sequence) —— 父节点 + SUB_NODE 子节点
"""

import asyncio
import sys
import os

# 将项目根目录加入 sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from workflow import Workflow, NodeRegistry
from workflow.core.eEdgeType import EEdgeType


# ─── 示例 1: 线性工作流 ────────────────────────────────────────────

async def example_linear_workflow():
    """BeginPlay → LLM(数学计算) → LLM(总结回复)。

    AddNodeAuto 返回自动生成的 ID，捕获后用于连边。
    """
    print("─" * 40)
    print("[示例1] 线性工作流: BeginPlay → LLM → LLM")

    wf = Workflow(name="LinearDemo")

    g = wf.graph
    # AddNodeAuto 返回自动分配的 ID（负值）
    start = g.AddNodeAuto(NodeRegistry.Get("Action/BeginPlay")())
    math  = g.AddNodeAuto(NodeRegistry.Get("Action/LLMClientCall")(
        name="数学计算",
        ModelName="deepseek-mid",
        SystemPrompt="你是数学助手，简洁回答。",
        UserMessage="1+1等于几？",
    ))
    end   = g.AddNodeAuto(NodeRegistry.Get("Action/LLMClientCall")(
        name="总结",
        ModelName="deepseek-mid",
        SystemPrompt="你是总结助手，用一句话总结。",
        UserMessage="把前面的计算结果总结一下",
    ))

    # 链式连边
    g.AddEdge(start, math).AddEdge(math, end)

    print(f"  节点数: {g.NodeCount}, 边数: {g.EdgeCount}")

    ctx = await wf.ExecuteAsync()
    reply = ctx.Get("Response")
    print(f"  最终回复: {reply[:120]}")
    assert reply and len(reply) > 0
    print("  ✓ 通过")


# ─── 示例 2: 含延迟的多步骤 ────────────────────────────────────────

async def example_with_delay():
    """BeginPlay → LLM(写作) → Delay(2s) → LLM(润色)。

    展示如何在多步骤流程中插入 Delay 节点。
    """
    print("─" * 40)
    print("[示例2] 含延迟: BeginPlay → LLM → Delay → LLM")

    wf = Workflow(name="DelayDemo")
    g = wf.graph

    a = g.AddNodeAuto(NodeRegistry.Get("Action/BeginPlay")())
    b = g.AddNodeAuto(NodeRegistry.Get("Action/LLMClientCall")(
        name="写作",
        ModelName="deepseek-mid",
        UserMessage="用两句话介绍人工智能。",
    ))
    c = g.AddNodeAuto(NodeRegistry.Get("Action/Delay")(Duration=2.0))
    d = g.AddNodeAuto(NodeRegistry.Get("Action/LLMClientCall")(
        name="润色",
        ModelName="deepseek-mid",
        SystemPrompt="你是文案润色助手。",
        UserMessage="请润色前面的内容，使其更生动。",
    ))

    g.AddEdge(a, b).AddEdge(b, c).AddEdge(c, d)

    ctx = await wf.ExecuteAsync()
    reply = ctx.Get("Response")
    print(f"  润色后: {reply[:120]}")
    assert reply and len(reply) > 0
    print("  ✓ 通过")


# ─── 示例 3: 复合节点 + 子节点 ─────────────────────────────────────

async def example_sequence_with_children():
    """Sequence 复合节点包含子节点（SUB_NODE 边），子节点顺序执行。

    BeginPlay → Sequence ──SUB_NODE──→ LLM(步骤1)
                         ──SUB_NODE──→ LLM(步骤2)
    """
    print("─" * 40)
    print("[示例3] Sequence 复合节点: 两个子 LLM 顺序执行")

    wf = Workflow(name="SequenceDemo")
    g = wf.graph

    entry = g.AddNodeAuto(NodeRegistry.Get("Action/BeginPlay")())
    seq   = g.AddNodeAuto(NodeRegistry.Get("Composite/Sequence")(name="多步骤"))
    step1 = g.AddNodeAuto(NodeRegistry.Get("Action/LLMClientCall")(
        name="步骤1-计算",
        ModelName="deepseek-mid",
        UserMessage="1+2等于几？请直接回答数字。",
    ))
    step2 = g.AddNodeAuto(NodeRegistry.Get("Action/LLMClientCall")(
        name="步骤2-总结",
        ModelName="deepseek-mid",
        UserMessage="用一句话总结：什么是工作流引擎？",
    ))

    # OUT 边连接入口到 Sequence，SUB_NODE 边连接父节点到子节点
    g.AddEdge(entry, seq) \
     .AddEdge(seq, step1, EEdgeType.SUB_NODE) \
     .AddEdge(seq, step2, EEdgeType.SUB_NODE)

    ctx = await wf.ExecuteAsync()
    reply = ctx.Get("Response")
    print(f"  最终回复: {reply[:120]}")
    assert reply and len(reply) > 0
    print("  ✓ 通过")


# ─── 主入口 ───────────────────────────────────────────────────────

async def main():
    print("程序化构建 Workflow — 使用示例")
    print("=" * 40)

    await example_linear_workflow()
    await example_with_delay()
    await example_sequence_with_children()

    print("=" * 40)
    print("全部示例完成 ✓")


if __name__ == "__main__":
    asyncio.run(main())
