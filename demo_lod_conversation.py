"""LOD 分级对话压测 Demo —— 验证多轮对话中 LOD 加载、压缩、落盘是否正常触发。

配置缩小阈值使 LOD 行为容易观察：
  - tokenBudget=4096     → 极小预算，2-3 轮即触发压缩
  - compactThreshold=0.5 → 50% 占用即压缩
  - keepRecentTurns=2    → 仅保留最近 2 轮
  - lod3LineThreshold=20 → 超过 20 行即判定 LOD3
  - persistCharThreshold=500 → 超过 500 字符即落盘
"""

from __future__ import annotations

import asyncio
import sys
import os

# 确保项目根目录在 sys.path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from llm.llmManager import LLMManager
from agent import Agent, AgentConfig, AgentStreamEvent, EAgentStreamEventType, EAgentState


# ---- 低阈值配置，容易触发 LOD 行为 ----

def BuildLowThresholdConfig() -> AgentConfig:
    """构建低阈值 AgentConfig，使 LOD / 压缩 / 落盘快速触发。"""
    return AgentConfig(
        maxTurns=10,
        autoCompact=True,

        # 极小 token 预算 → 2-3 轮即超预算触发压缩
        maxTokens=8192,
        reserveTokens=1024,
        tokenBudget=4096,
        compactThreshold=0.5,

        # 最近轮数窗口缩小
        recentTurnCount=2,
        keepRecentTurns=2,

        # LOD3 阈值极低，工具结果极易判定为 EXTERNAL_ONLY
        lod3LineThreshold=20,
        lod3SizeThreshold=500,

        # 落盘阈值极低
        enablePersist=True,
        persistCharThreshold=500,
        persistPreviewChars=100,

        # 外存目录
        storeDir=".contex/store_demo",
        logDir=".contex/log_demo",
        logFormat="TEXT",

        # 关闭 rules/skills/mcp 扫描（demo 不依赖本地文件）
        rulesDir="",
        skillsDir="",
        mcpJsonPath="",
        workspaceRoot=PROJECT_ROOT,
    )


# ---- 事件打印 ----

EVENT_ICONS = {
    EAgentStreamEventType.TEXT_DELTA: "📝",
    EAgentStreamEventType.TOOL_START: "🔧",
    EAgentStreamEventType.TOOL_RESULT: "📦",
    EAgentStreamEventType.STATE_CHANGE: "🔄",
    EAgentStreamEventType.TURN_START: "▶️",
    EAgentStreamEventType.ERROR: "❌",
    EAgentStreamEventType.DONE: "✅",
}

STATE_LABELS = {
    EAgentState.IDLE: "IDLE",
    EAgentState.THINKING: "THINKING",
    EAgentState.ACTING: "ACTING",
    EAgentState.FINISHED: "FINISHED",
    EAgentState.ERROR: "ERROR",
}


def PrintEvent(event: AgentStreamEvent, verbose: bool = False) -> None:
    """打印单个 AgentStreamEvent。"""
    icon = EVENT_ICONS.get(event.eventType, "?")

    if event.eventType == EAgentStreamEventType.TEXT_DELTA:
        print(event.content, end="", flush=True)

    elif event.eventType == EAgentStreamEventType.TOOL_START:
        argsPreview = ""
        if event.toolArgs:
            for k, v in event.toolArgs.items():
                valStr = str(v)
                if len(valStr) > 80:
                    valStr = valStr[:80] + "..."
                argsPreview += f"  {k}: {valStr}\n"
        print(f"\n{icon} 工具调用: {event.toolName} (turn={event.turnIndex})")
        if argsPreview:
            print(argsPreview.rstrip())

    elif event.eventType == EAgentStreamEventType.TOOL_RESULT:
        content = event.content or ""
        if len(content) > 200:
            content = content[:200] + f"... ({len(event.content)} chars total)"
        print(f"\n{icon} 工具结果: {event.toolName} | {content}")

    elif event.eventType == EAgentStreamEventType.STATE_CHANGE:
        stateLabel = STATE_LABELS.get(event.state, str(event.state)) if event.state else "?"
        print(f"\n{icon} 状态变更: {stateLabel} (turn={event.turnIndex})")

    elif event.eventType == EAgentStreamEventType.TURN_START:
        print(f"\n{'='*60}")
        print(f"{icon} Turn {event.turnIndex} 开始")
        print(f"{'='*60}")

    elif event.eventType == EAgentStreamEventType.ERROR:
        print(f"\n{icon} 错误: {event.error} (turn={event.turnIndex})")

    elif event.eventType == EAgentStreamEventType.DONE:
        print(f"\n{icon} 本轮结束\n")


# ---- 多轮对话 ----

QUESTIONS = [
    "请使用 search_web 工具搜索今天中国A股市场的财经新闻，告诉我有什么重要动态",
    "请使用 search_web 工具搜索美股纳斯达克最新行情，然后用 fetch_content 抓取其中一篇详细报道的内容",
    "请使用 search_web 工具搜索近期人民币兑美元汇率的变化趋势",
    "请使用 search_web 工具搜索欧洲央行最新利率决议，然后用 fetch_content 抓取一篇详细分析",
    "结合前面所有搜索结果，给出一份简短的今日全球金融市场概览",
]


async def RunConversationAsync() -> None:
    """运行多轮对话，观察 LOD 行为。"""
    print("=" * 60)
    print("  LOD 分级对话压测 Demo")
    print("  配置: tokenBudget=4096, compactThreshold=0.5")
    print("        keepRecentTurns=2, lod3LineThreshold=20")
    print("        persistCharThreshold=500")
    print("=" * 60)

    # 初始化 LLM
    LLMManager.InitFromPath(os.path.join(PROJECT_ROOT, "workspace", "models.json"))
    llm = LLMManager.GetProvider("deepseek-mid")
    print(f"\n使用模型: {llm}\n")

    # 构建 Agent（低阈值配置）
    config = BuildLowThresholdConfig()
    agent = Agent(llm=llm, config=config)

    # 加载内置工具（search_web / fetch_content 等）
    from agent.component.tool.toolComponent import ToolComponent
    toolComp = agent.GetComponent(ToolComponent)
    loadedCount = toolComp.LoadBuiltins()
    print(f"已加载内置工具: {loadedCount} 个\n")

    # 注入工具使用指令（让模型主动调用 search_web / fetch_content）
    from agent.component.contex.contextComponent import ContextComponent
    from agent.component.contex.eContextLodLevel import EContextLodLevel
    from agent.component.llm.llmComponent import LLMComponent
    from common.const import ERole
    ctxComp = agent.GetComponent(ContextComponent)
    ctxComp.Ingest(
        ERole.SYSTEM,
        (
            "<tool_usage_policy>\n"
            "你是一个财经研究助手。对于用户关于实时行情、新闻、数据的请求，\n"
            "你 MUST 优先使用 search_web 和 fetch_content 工具获取最新信息，\n"
            "而非依赖训练数据中的旧知识。\n"
            "每次搜索后请基于搜索结果回答，不要凭记忆编造。\n"
            "</tool_usage_policy>"
        ),
        lodLevel=EContextLodLevel.RESIDENT,
    )
    print("已注入工具使用策略")

    # 无需强制 tool_choice——非流式模式已能正确解析工具调用
    print("已注入工具使用策略\n")

    # 多轮对话
    from agent.component.llm.llmComponent import LLMComponent
    llmComp = agent.GetComponent(LLMComponent)
    for roundIdx, question in enumerate(QUESTIONS):
        print("\n" + "=" * 60)
        print(f"  第 {roundIdx + 1} 轮对话")
        print(f"  用户: {question}")
        print("=" * 60)

        # 记录本轮前的上下文状态
        from agent.component.contex.contextComponent import ContextComponent
        from agent.component.session.sessionComponent import SessionComponent
        ctxComp = agent.GetComponent(ContextComponent)
        sessionComp = agent.GetComponent(SessionComponent)
        if ctxComp is not None and sessionComp is not None:
            msgCount = len(sessionComp.messages)
            estTokens = ctxComp.EstimatedTokens
            hasCompressed = sessionComp.CompressedSummary is not None
            print(f"  [上下文状态] 消息数={msgCount}, 估算Token={estTokens}, 已压缩={hasCompressed}")

        # 运行 Agent（非流式，确保 DeepSeek 工具调用被正确解析）
        async for event in agent.RunInvokeAsync(question):
            PrintEvent(event)

        # 检查工具绑定
        if llmComp is not None:
            boundTools = llmComp.RequestParams.tools
            toolNames = [t.name for t in boundTools] if boundTools else []
            print(f"  [工具绑定] 已绑定 {len(toolNames)} 个工具: {toolNames}")

        # 本轮结束后上下文状态
        if ctxComp is not None and sessionComp is not None:
            msgCount = len(sessionComp.messages)
            estTokens = ctxComp.EstimatedTokens
            hasCompressed = sessionComp.CompressedSummary is not None
            compressedUpTo = sessionComp.CompressedUpToTurnIndex
            print(f"\n  [本轮后上下文状态] 消息数={msgCount}, 估算Token={estTokens}, "
                  f"已压缩={hasCompressed}, 压缩覆盖至Turn={compressedUpTo}")

            # 检查 LOD 分布
            lodDistribution = {0: 0, 1: 0, 2: 0, 3: 0}
            for msg in sessionComp.messages:
                if not msg.isCompacted:
                    lodDistribution[msg.lodLevel] = lodDistribution.get(msg.lodLevel, 0) + 1
            print(f"  [LOD 分布] RESIDENT={lodDistribution[0]}, SUMMARIZABLE={lodDistribution[1]}, "
                  f"DISCARDABLE={lodDistribution[2]}, EXTERNAL_ONLY={lodDistribution[3]}")

            # 检查冷卸载
            agedOutCount = sum(1 for m in sessionComp.messages if m.isAgedOut)
            print(f"  [冷卸载] 已标记 isAgedOut={agedOutCount}")

        print()

    # 最终清理
    agent.Destroy()
    print("\n" + "=" * 60)
    print("  Demo 运行完毕，Agent 已销毁")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(RunConversationAsync())
