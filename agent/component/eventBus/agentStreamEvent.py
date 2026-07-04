"""Agent 流式事件 —— 供 webView 实时渲染的标准化事件数据。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Optional

from agent.component.tool.toolResult import ToolResult
from agent.component.data.eAgentState import EAgentState


class EAgentStreamEventType(IntEnum):
    """Agent 流式事件类型，按 ReAct 执行流时序排列。

    Attributes:
        TURN_START: 推理轮次开始。
        THINKING_DELTA: 思考增量内容。
        THINKING_COMPLETE: 思考阶段完成，携带完整思考文本。
        TEXT_DELTA: 文本增量内容。
        TEXT_COMPLETE: 文本流式输出完毕，携带完整文本。
        TOOL_START: 工具调用开始。
        TOOL_RESULT: 工具执行结果。
        STATE_CHANGE: Agent 状态迁移。
        COMPACTION: 上下文压缩事件（冷卸载 / LLM 摘要 / 丢弃）。
        ERROR: 错误事件。
        DONE: 本轮结束。
    """

    TURN_START = 0
    THINKING_DELTA = 1
    THINKING_COMPLETE = 2
    TEXT_DELTA = 3
    TEXT_COMPLETE = 4
    TOOL_START = 5
    TOOL_RESULT = 6
    STATE_CHANGE = 7
    COMPACTION = 8
    ERROR = 9
    DONE = 10


@dataclass(slots=True)
class AgentStreamEvent:
    """Agent 流式事件

    Attributes:
        eventType: 事件类型标识。
        content: 文本内容。
        toolName: 工具名称（TOOL_START / TOOL_RESULT 时填充）。
        toolArgs: 工具调用参数（TOOL_START 时填充）。
        toolResult: 工具执行结果（TOOL_RESULT 时填充）。
        state: 状态迁移目标（STATE_CHANGE 时填充）。
        turnIndex: 当前推理轮次序号。
        tokenSaved: 压缩释放的 token 数（COMPACTION 时填充）。
        compactedCount: 压缩涉及的消息数（COMPACTION 时填充）。
        error: 错误信息（ERROR 时填充）。
    """

    eventType: EAgentStreamEventType
    content: str = ""
    toolName: str = ""
    toolArgs: Optional[dict] = None
    toolResult: Optional[ToolResult] = None
    state: Optional[EAgentState] = None
    turnIndex: int = 0
    tokenSaved: int = 0
    compactedCount: int = 0
    error: str = ""

    # ---- 工厂方法 ----

    @staticmethod
    def TextDelta(content: str, turnIndex: int = 0) -> AgentStreamEvent:
        return AgentStreamEvent(eventType=EAgentStreamEventType.TEXT_DELTA, content=content, turnIndex=turnIndex)

    @staticmethod
    def ToolStart(toolName: str, toolArgs: dict, turnIndex: int = 0) -> AgentStreamEvent:
        return AgentStreamEvent(eventType=EAgentStreamEventType.TOOL_START, toolName=toolName, toolArgs=toolArgs, turnIndex=turnIndex)

    @staticmethod
    def ToolResultEvent(toolName: str, result: ToolResult, turnIndex: int = 0) -> AgentStreamEvent:
        return AgentStreamEvent(
            eventType=EAgentStreamEventType.TOOL_RESULT,
            toolName=toolName,
            content=result.ToLLMContent(),
            toolResult=result,
            turnIndex=turnIndex,
        )

    @staticmethod
    def StateChange(state: EAgentState, turnIndex: int = 0) -> AgentStreamEvent:
        return AgentStreamEvent(eventType=EAgentStreamEventType.STATE_CHANGE, state=state, turnIndex=turnIndex)

    @staticmethod
    def TurnStart(turnIndex: int) -> AgentStreamEvent:
        return AgentStreamEvent(eventType=EAgentStreamEventType.TURN_START, turnIndex=turnIndex)

    @staticmethod
    def Compaction(tokenSaved: int = 0, compactedCount: int = 0, turnIndex: int = 0) -> AgentStreamEvent:
        return AgentStreamEvent(
            eventType=EAgentStreamEventType.COMPACTION,
            tokenSaved=tokenSaved,
            compactedCount=compactedCount,
            turnIndex=turnIndex,
        )

    @staticmethod
    def ErrorEvent(error: str, turnIndex: int = 0) -> AgentStreamEvent:
        return AgentStreamEvent(eventType=EAgentStreamEventType.ERROR, error=error, turnIndex=turnIndex)

    @staticmethod
    def Done() -> AgentStreamEvent:
        return AgentStreamEvent(eventType=EAgentStreamEventType.DONE)

    @staticmethod
    def TextComplete(content: str, turnIndex: int = 0) -> AgentStreamEvent:
        return AgentStreamEvent(eventType=EAgentStreamEventType.TEXT_COMPLETE, content=content, turnIndex=turnIndex)

    @staticmethod
    def ThinkingDelta(content: str, turnIndex: int = 0) -> AgentStreamEvent:
        return AgentStreamEvent(eventType=EAgentStreamEventType.THINKING_DELTA, content=content, turnIndex=turnIndex)

    @staticmethod
    def ThinkingComplete(content: str, turnIndex: int = 0) -> AgentStreamEvent:
        return AgentStreamEvent(eventType=EAgentStreamEventType.THINKING_COMPLETE, content=content, turnIndex=turnIndex)
