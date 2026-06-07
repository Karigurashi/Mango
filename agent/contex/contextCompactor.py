"""分级压缩器 —— 按 LOD 三级紧急度执行上下文压缩，LLM 驱动摘要。"""

from __future__ import annotations

from typing import NamedTuple, TYPE_CHECKING

from common.const import ERole
from llm.provider.chatMessage import ChatMessage

from .contextConfig import ContextConfig
from .contextMessage import ContextMessage
from .eCompactionUrgency import ECompactionUrgency
from .eContextLodLevel import EContextLodLevel
from .tokenEstimator import TokenEstimator

if TYPE_CHECKING:
    from llm.baseLLM import BaseLLM


class CompactionResult(NamedTuple):
    """压缩操作的完整结果。

    Attributes:
        messages: 压缩后的消息列表。
        compactedIds: 被压缩（摘要化或丢弃）的原始消息 ID 列表。
        newSummaryMessages: 新生成的摘要消息列表（供回写 Session）。
    """

    messages: list[ContextMessage]
    compactedIds: list[str]
    newSummaryMessages: list[ContextMessage]


class ContextCompactor:
    """按 LOD 分级执行上下文压缩。

    三级紧急度：
    - 轻度（占用 > 100%）：仅丢弃最旧的 LOD 2（不调用 LLM）
    - 中度（占用 > 150%）：丢弃全部 LOD 2 + LLM 逐条摘要最旧 LOD 1
    - 重度（占用 > 200%）：丢弃全部 LOD 2 + LLM 批量摘要全部 LOD 1

    LOD 0 在任何情况下都不可修改。

    当 BaseLLM 不可用时，退化到截断摘要兜底。
    """

    def __init__(
        self,
        config: ContextConfig,
        tokenEstimator: TokenEstimator,
        llm: BaseLLM | None = None,
    ) -> None:
        self._config = config
        self._tokenEstimator = tokenEstimator
        self._llm = llm

    # ---- 公开入口 ----

    async def CompactByLodAsync(
        self, messages: list[ContextMessage], targetTokens: int
    ) -> CompactionResult:
        """按 LOD 分级异步压缩消息列表，使其 token 数不超过 targetTokens。

        Args:
            messages: 待压缩的消息列表。
            targetTokens: 目标 token 上限。

        Returns:
            CompactionResult，含压缩后消息、被压缩 ID、新摘要消息。
        """
        currentTokens = self._tokenEstimator.EstimateMessages(messages)
        if currentTokens <= targetTokens:
            return CompactionResult(
                messages=messages,
                compactedIds=[],
                newSummaryMessages=[],
            )

        urgency = self._ClassifyUrgency(currentTokens, targetTokens)

        lod0 = [m for m in messages if m.lodLevel == EContextLodLevel.RESIDENT]
        lod1 = [m for m in messages if m.lodLevel == EContextLodLevel.SUMMARIZABLE]
        lod2 = [m for m in messages if m.lodLevel == EContextLodLevel.DISCARDABLE]

        if urgency == ECompactionUrgency.MILD:
            return self._CompactMild(lod0, lod1, lod2, targetTokens)
        elif urgency == ECompactionUrgency.MODERATE:
            return await self._CompactModerateAsync(lod0, lod1, lod2, targetTokens)
        else:
            return await self._CompactSevereAsync(lod0, lod1, lod2, targetTokens)

    # ---- 紧急度判定 ----

    def _ClassifyUrgency(self, currentTokens: int, targetTokens: int) -> ECompactionUrgency:
        ratio = currentTokens / targetTokens if targetTokens > 0 else float("inf")
        if ratio <= 1.0:
            return ECompactionUrgency.NONE
        if ratio <= 1.5:
            return ECompactionUrgency.MILD
        if ratio <= 2.0:
            return ECompactionUrgency.MODERATE
        return ECompactionUrgency.SEVERE

    # ---- 轻度：丢弃最旧 LOD 2（同步，无 LLM） ----

    def _CompactMild(
        self,
        lod0: list[ContextMessage],
        lod1: list[ContextMessage],
        lod2: list[ContextMessage],
        targetTokens: int,
    ) -> CompactionResult:
        """轻度压缩：丢弃最旧的 LOD 2 消息，直到满足预算。"""
        result = list(lod0) + list(lod1)
        lod2Sorted = sorted(lod2, key=lambda m: m.turnIndex)
        remaining = list(lod2Sorted)
        discarded: list[ContextMessage] = []

        currentTokens = self._tokenEstimator.EstimateMessages(result + remaining)
        while currentTokens > targetTokens and remaining:
            discarded.append(remaining.pop(0))
            currentTokens = self._tokenEstimator.EstimateMessages(result + remaining)

        return CompactionResult(
            messages=result + remaining,
            compactedIds=[m.messageId for m in discarded],
            newSummaryMessages=[],
        )

    # ---- 中度：丢全部 LOD 2 + LLM 逐条摘要 LOD 1 ----

    async def _CompactModerateAsync(
        self,
        lod0: list[ContextMessage],
        lod1: list[ContextMessage],
        lod2: list[ContextMessage],
        targetTokens: int,
    ) -> CompactionResult:
        """中度压缩：丢弃全部 LOD 2 + LLM 摘要化最旧 LOD 1。"""
        compactedIds = [m.messageId for m in lod2]
        newSummaryMessages: list[ContextMessage] = []
        result = list(lod0)
        lod1Sorted = sorted(lod1, key=lambda m: m.turnIndex, reverse=True)

        currentTokens = self._tokenEstimator.EstimateMessages(result + lod1)
        for i, msg in enumerate(lod1Sorted):
            if currentTokens <= targetTokens:
                break
            summary = await self._SummarizeMessageAsync(msg)
            compactedIds.append(msg.messageId)
            summaryMsg = ContextMessage(
                chatMessage=ChatMessage(role=msg.role, content=summary),
                lodLevel=EContextLodLevel.SUMMARIZABLE,
                turnIndex=msg.turnIndex,
                summarizedFrom=[msg.messageId],
            )
            newSummaryMessages.append(summaryMsg)
            lod1Sorted[i] = summaryMsg
            currentTokens = self._tokenEstimator.EstimateMessages(
                result + list(reversed(lod1Sorted))
            )

        return CompactionResult(
            messages=result + list(reversed(lod1Sorted)),
            compactedIds=compactedIds,
            newSummaryMessages=newSummaryMessages,
        )

    # ---- 重度：丢全部 LOD 2 + LLM 批量摘要全部 LOD 1 ----

    async def _CompactSevereAsync(
        self,
        lod0: list[ContextMessage],
        lod1: list[ContextMessage],
        lod2: list[ContextMessage],
        targetTokens: int,
    ) -> CompactionResult:
        """重度压缩：丢弃全部 LOD 2 + LLM 批量摘要全部 LOD 1。"""
        _ = targetTokens
        compactedIds = [m.messageId for m in lod2]
        newSummaryMessages: list[ContextMessage] = []
        result = list(lod0)

        if lod1:
            combinedText = "\n---\n".join(
                f"[{m.role}] {m.content}" for m in lod1
            )
            summary = await self._SummarizeBatchAsync(combinedText)
            compactedIds.extend(m.messageId for m in lod1)
            summaryMsg = ContextMessage(
                chatMessage=ChatMessage(role=ERole.SYSTEM, content=f"[历史对话摘要]\n{summary}"),
                lodLevel=EContextLodLevel.SUMMARIZABLE,
                turnIndex=-1,
                summarizedFrom=[m.messageId for m in lod1],
            )
            newSummaryMessages.append(summaryMsg)
            result.append(summaryMsg)

        return CompactionResult(
            messages=result,
            compactedIds=compactedIds,
            newSummaryMessages=newSummaryMessages,
        )

    # ---- LLM 摘要核心 ----

    async def _SummarizeMessageAsync(self, msg: ContextMessage) -> str:
        """对单条消息调用 LLM 生成摘要，LLM 不可用时退化到截断。"""
        if self._llm is None:
            return self._TruncateText(
                msg.content, self._config.summaryMaxTokens * 4
            )

        prompt = self._config.compactionPrompt or self._config.DEFAULT_SINGLE_SUMMARY_PROMPT
        userContent = f"{prompt}\n\n<message>\n{msg.content}\n</message>"

        try:
            response = await self._llm.InvokeAsync(
                [ChatMessage.User(userContent)],
                temperature=0.2,
                maxTokens=self._config.summaryMaxTokens,
            )
            return response.content.strip()
        except Exception:
            return self._TruncateText(
                msg.content, self._config.summaryMaxTokens * 4
            )

    async def _SummarizeBatchAsync(self, combinedText: str) -> str:
        """对批量文本调用 LLM 生成摘要，LLM 不可用时退化到截断。"""
        if self._llm is None:
            return self._TruncateText(
                combinedText, self._config.batchSummaryMaxTokens * 4
            )

        prompt = self._config.compactionPrompt or self._config.DEFAULT_BATCH_SUMMARY_PROMPT
        userContent = f"{prompt}\n\n<conversation>\n{combinedText}\n</conversation>"

        try:
            response = await self._llm.InvokeAsync(
                [ChatMessage.User(userContent)],
                temperature=0.2,
                maxTokens=self._config.batchSummaryMaxTokens,
            )
            return response.content.strip()
        except Exception:
            return self._TruncateText(
                combinedText, self._config.batchSummaryMaxTokens * 4
            )

    # ---- 增量批量压缩（强制合并为单条摘要） ----

    async def CompactBatchAsync(
        self, messages: list[ContextMessage], targetTokens: int
    ) -> CompactionResult:
        """无条件批量压缩：丢弃全部 LOD 2，将所有 LOD 1 合并为单条摘要。

        用于增量压缩场景（已有旧摘要时），确保始终只有 1 条摘要消息。

        Args:
            messages: 待压缩的消息列表。
            targetTokens: 目标 token 上限。

        Returns:
            CompactionResult，newSummaryMessages 中始终只有 0 或 1 条。
        """
        _ = targetTokens
        lod0 = [m for m in messages if m.lodLevel == EContextLodLevel.RESIDENT]
        lod1 = [m for m in messages if m.lodLevel == EContextLodLevel.SUMMARIZABLE]
        lod2 = [m for m in messages if m.lodLevel == EContextLodLevel.DISCARDABLE]

        compactedIds = [m.messageId for m in lod2]
        newSummaryMessages: list[ContextMessage] = []
        result = list(lod0)

        if lod1:
            combinedText = "\n---\n".join(
                f"[{m.role}] {m.content}" for m in lod1
            )
            summary = await self._SummarizeBatchAsync(combinedText)
            compactedIds.extend(m.messageId for m in lod1)
            summaryMsg = ContextMessage(
                chatMessage=ChatMessage(role=ERole.SYSTEM, content=f"[历史对话摘要]\n{summary}"),
                lodLevel=EContextLodLevel.SUMMARIZABLE,
                turnIndex=-1,
                summarizedFrom=[m.messageId for m in lod1],
            )
            newSummaryMessages.append(summaryMsg)
            result.append(summaryMsg)

        return CompactionResult(
            messages=result,
            compactedIds=compactedIds,
            newSummaryMessages=newSummaryMessages,
        )

    # ---- 截断兜底 ----

    @staticmethod
    def _TruncateText(text: str, maxChars: int) -> str:
        """截断文本到指定字符数，保留完整性。"""
        if len(text) <= maxChars:
            return text
        return text[:maxChars] + "…"

    def __repr__(self) -> str:
        hasLlm = self._llm is not None
        return (
            f"ContextCompactor(keepRecent={self._config.keepRecentTurns}, "
            f"llm={hasLlm})"
        )
