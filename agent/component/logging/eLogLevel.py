"""日志级别枚举 —— 控制 LoggingComponent 的事件过滤阈值。"""

from enum import IntEnum


class ELogLevel(IntEnum):
    """日志级别（与常见日志框架语义一致）。

    Attributes:
        INFO: 常规可观测事件（默认级别）。
        WARNING: 异常但可恢复的事件（重试、超时回退等）。
        ERROR: 失败事件（LLM/工具调用失败、Run 异常结束）。
    """

    INFO = 0
    WARNING = 1
    ERROR = 2

    def __repr__(self) -> str:
        return f"ELogLevel.{self.name}"
