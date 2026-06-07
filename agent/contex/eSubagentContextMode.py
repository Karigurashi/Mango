"""子Agent 上下文模式枚举。"""

from enum import Enum


class ESubagentContextMode(Enum):
    """子Agent 的上下文继承模式。

    Attributes:
        ISOLATED: 完全隔离，子Agent 从空白上下文开始，仅继承父 System Prompt（LOD 0）。
        FORK: 复制父 Agent 全部消息，子Agent 可独立压缩/修改。
    """

    ISOLATED = "isolated"
    FORK = "fork"
