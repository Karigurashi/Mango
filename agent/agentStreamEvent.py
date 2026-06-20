"""Agent 流式事件 —— 供 webView 实时渲染的标准化事件数据。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Optional

from agent.component.tool.toolResult import ToolResult

from agent.component.data.eAgentState import EAgentState


class EAgentStreamEventType(IntEnum):
    """Agent 流式事件类型。

    Attributes:
        TEXT_DELTA: 文本增量内容。
        TOOL_START: 工具调用开始。
        TOOL_RESULT: 工具执行结果。
        STATE_CHANGE: Agent 状态迁移。
        TURN_START: 推理轮次开始。
        ERROR: 错误事件。
        DONE: 本轮结束。
    """

    TEXT_DELTA = 0
    TOOL_START = 1
    TOOL_RESULT = 2
    STATE_CHANGE = 3
    TURN_START = 4
    ERROR = 5
    DONE = 6


@dataclass(frozen=True, slots=True)
class AgentStreamEvent:
    """Agent 流式事件，供 webView 实时渲染。

    Attributes:
        eventType: 事件类型标识（TEXT_DELTA / TOOL_START / TOOL_RESULT / STATE_CHANGE / TURN_START / ERROR / DONE）。
        content: 文本内容（TEXT_DELTA / TOOL_RESULT 时填充）。
        toolName: 工具名称（TOOL_START / TOOL_RESULT 时填充）。
        toolArgs: 工具调用参数（TOOL_START 时填充）。
        toolResult: 工具执行结果（TOOL_RESULT 时填充）。
        state: 状态迁移目标（STATE_CHANGE 时填充）。
        turnIndex: 当前推理轮次序号。
        error: 错误信息（ERROR 时填充）。
    """

    eventType: EAgentStreamEventType
    content: str = ""
    toolName: str = ""
    toolArgs: Optional[dict] = None
    toolResult: Optional[ToolResult] = None
    state: Optional[EAgentState] = None
    turnIndex: int = 0
    error: str = ""

    # ---- 工厂方法 ----

    @staticmethod
    def TextDelta(content: str, turnIndex: int = 0) -> "AgentStreamEvent":
        return AgentStreamEvent(eventType=EAgentStreamEventType.TEXT_DELTA, content=content, turnIndex=turnIndex)

    @staticmethod
    def ToolStart(toolName: str, toolArgs: dict, turnIndex: int = 0) -> "AgentStreamEvent":
        return AgentStreamEvent(
            eventType=EAgentStreamEventType.TOOL_START, toolName=toolName, toolArgs=toolArgs, turnIndex=turnIndex,
        )

    @staticmethod
    def ToolResultEvent(toolName: str, result: ToolResult, turnIndex: int = 0) -> "AgentStreamEvent":
        return AgentStreamEvent(
            eventType=EAgentStreamEventType.TOOL_RESULT, toolName=toolName, content=result.ToLLMContent(),
            toolResult=result, turnIndex=turnIndex,
        )

    @staticmethod
    def StateChange(state: EAgentState, turnIndex: int = 0) -> "AgentStreamEvent":
        return AgentStreamEvent(eventType=EAgentStreamEventType.STATE_CHANGE, state=state, turnIndex=turnIndex)

    @staticmethod
    def TurnStart(turnIndex: int) -> "AgentStreamEvent":
        return AgentStreamEvent(eventType=EAgentStreamEventType.TURN_START, turnIndex=turnIndex)

    @staticmethod
    def ErrorEvent(error: str, turnIndex: int = 0) -> "AgentStreamEvent":
        return AgentStreamEvent(eventType=EAgentStreamEventType.ERROR, error=error, turnIndex=turnIndex)

    @staticmethod
    def Done() -> "AgentStreamEvent":
        return AgentStreamEvent(eventType=EAgentStreamEventType.DONE)
