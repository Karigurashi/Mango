"""压缩紧急度枚举 —— 控制压缩策略的分级选择。"""

from enum import Enum


class ECompactionUrgency(Enum):
    """上下文压缩紧急度分级 —— 决定采用何种压缩策略。

    Attributes:
        NONE (0): 无需压缩（token 在预算内）。
        MILD (1): 轻度压缩（丢弃最旧 LOD 2 消息）。
        MODERATE (2): 中度压缩（丢弃全部 LOD 2 + LLM 逐条摘要最旧 LOD 1）。
        SEVERE (3): 重度压缩（丢弃全部 LOD 2 + LLM 批量摘要全部 LOD 1）。
    """

    NONE = 0
    MILD = 1
    MODERATE = 2
    SEVERE = 3

    def __repr__(self) -> str:
        return f"ECompactionUrgency.{self.name}"
