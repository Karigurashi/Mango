"""Token 估算器 —— 估算文本/消息的 token 数量，用于 LOD 过滤决策。"""

from __future__ import annotations

from .contextMessage import ContextMessage


class TokenEstimator:
    """Token 数量估算器。

    默认使用字符数/4 的近似算法（英文约 4 字符/token），
    后续可接入 tiktoken 实现精确估算。

    Attributes:
        charsPerToken: 近似估算中每 token 的平均字符数（默认 4）。
        overheadPerMessage: 每条消息的 role/metadata 固定开销（默认 4 token）。
    """

    def __init__(self, charsPerToken: float = 4.0, overheadPerMessage: int = 4) -> None:
        self.charsPerToken = charsPerToken
        self.overheadPerMessage = overheadPerMessage

    def Estimate(self, text: str) -> int:
        """估算单段文本的 token 数。"""
        if not text:
            return 0
        return max(1, int(len(text) / self.charsPerToken))

    def EstimateMessage(self, msg: ContextMessage) -> int:
        """估算单条 ContextMessage 的 token 数（含 role/metadata 开销）。"""
        return self.overheadPerMessage + self.Estimate(msg.content)

    def EstimateMessages(self, messages: list[ContextMessage]) -> int:
        """估算消息列表的总 token 数。"""
        return sum(self.EstimateMessage(m) for m in messages)

    def EstimateByLod(self, messages: list[ContextMessage]) -> dict[str, int]:
        """按 LOD 分组统计 token 占用。

        Returns:
            {"LOD0": N, "LOD1": N, "LOD2": N, "LOD3": N}
        """
        stats: dict[str, int] = {"LOD0": 0, "LOD1": 0, "LOD2": 0, "LOD3": 0}
        for msg in messages:
            key = f"LOD{msg.lodLevel.value}"
            stats[key] = stats.get(key, 0) + self.EstimateMessage(msg)
        return stats

    def IsWithinBudget(self, messages: list[ContextMessage], budget: int) -> bool:
        """判断消息列表是否在 token 预算内。"""
        return self.EstimateMessages(messages) <= budget

    def __repr__(self) -> str:
        return f"TokenEstimator(charsPerToken={self.charsPerToken})"
