"""结构化日志事件类型枚举 —— 标识 Agent 运行时各类可观测事件。"""

from enum import IntEnum


class ELogEventType(IntEnum):
    """结构化日志事件类型。

    Attributes:
        LLM_CALL: LLM 调用完成（流式/非流式）。
        TOOL_EXECUTION: 工具执行完成（单工具/批量）。
        COMPACTION: 上下文压缩完成。
        STATE_CHANGE: Agent 状态迁移。
        CONTEXT_LIFECYCLE: 上下文生命周期事件（Ingest/Assemble/Compact/AfterTurn）。
        RUN_START: 单次 Run 启动。
        RUN_END: 单次 Run 结束（正常/异常/超限）。
    """

    LLM_CALL = 0
    TOOL_EXECUTION = 1
    COMPACTION = 2
    STATE_CHANGE = 3
    CONTEXT_LIFECYCLE = 4
    RUN_START = 5
    RUN_END = 6

    def __repr__(self) -> str:
        return f"ELogEventType.{self.name}"
