"""LOD 分级管理器 —— 上下文组装的核心，负责分类、过滤、压缩。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from common.const import ERole

from .contentStore import ContentStore
from .contextCompactor import CompactionResult, ContextCompactor
from .contextConfig import ContextConfig
from .contextMessage import ContextMessage
from .eContextLodLevel import EContextLodLevel
from .tokenEstimator import TokenEstimator

if TYPE_CHECKING:
    from llm.baseLLM import BaseLLM


class ContextLodManager:
    """LOD 四级分级管理的核心实现。

    三个核心职责：
    1. ClassifyMessage —— 摄入时按 role + content + metadata 判定 LOD 等级
    2. AssembleMessages —— 组装时从 Session 的 ContextMessage 过滤、排序
    3. CompactMessages —— 压缩时按 LOD 分级处理，释放 token 空间
    """

    def __init__(
        self,
        config: ContextConfig,
        contentStore: ContentStore | None = None,
        tokenEstimator: TokenEstimator | None = None,
        llm: BaseLLM | None = None,
    ) -> None:
        self._config = config
        self._contentStore = contentStore or ContentStore(config.storeDir)
        self._tokenEstimator = tokenEstimator or TokenEstimator()
        self._compactor = ContextCompactor(
            config, self._tokenEstimator, llm
        )

    # ---- 1. 分类（仅 Ingest 阶段使用） ----

    def ClassifyMessage(
        self, role: ERole, content: str, metadata: dict | None = None
    ) -> EContextLodLevel:
        """判定消息的 LOD 等级。

        按 role + metadata 自动判定，工具结果额外按 config 阈值
        判定是否升级为 LOD 3 EXTERNAL_ONLY。

        Args:
            role: 消息角色。
            content: 消息内容。
            metadata: 扩展元数据。

        Returns:
            LOD 等级。
        """
        meta = metadata or {}
        lod = self._ClassifyLod(role, meta)

        # 工具结果按大小阈值覆盖
        if role == ERole.TOOL:
            return self._ClassifyToolResult(content)
        return lod

    @staticmethod
    def _ClassifyLod(role: ERole, metadata: dict) -> EContextLodLevel:
        """按 role + metadata 自动判定 LOD（不涉及 config 阈值）。"""
        if role == ERole.SYSTEM:
            return EContextLodLevel.RESIDENT
        if metadata.get("isThinking") is True:
            return EContextLodLevel.DISCARDABLE
        if metadata.get("isDecision") is True:
            return EContextLodLevel.SUMMARIZABLE
        if role == ERole.TOOL:
            return EContextLodLevel.DISCARDABLE
        if role in (ERole.USER, ERole.ASSISTANT):
            return EContextLodLevel.SUMMARIZABLE
        return EContextLodLevel.DISCARDABLE

    def _ClassifyToolResult(self, content: str) -> EContextLodLevel:
        """根据工具结果大小判定 LOD。"""
        lineCount = content.count("\n") + 1 if content else 0
        byteSize = len(content.encode("utf-8")) if content else 0

        if lineCount >= self._config.lod3LineThreshold or byteSize >= self._config.lod3SizeThreshold:
            return EContextLodLevel.EXTERNAL_ONLY
        return EContextLodLevel.DISCARDABLE

    # ---- 2. 组装（纯读取，不压缩，不写 Session） ----

    def AssembleMessages(
        self, messages: list[ContextMessage]
    ) -> list[ContextMessage]:
        """从 Session 的 ContextMessage 列表组装可发送的消息。

        消息保持 Session 原始追加顺序，摘要消息排最前。
        已压缩消息和 LOD 3 消息跳过。

        Args:
            messages: Session 中的 ContextMessage 列表。

        Returns:
            组装后的 ContextMessage 列表。
        """
        summaries: list[ContextMessage] = []
        regular: list[ContextMessage] = []

        for msg in messages:
            if msg.isCompacted:
                continue
            if not msg.lodLevel.ShouldInject():
                continue
            if msg.summarizedFrom:
                summaries.append(msg)
            else:
                regular.append(msg)

        return summaries + regular

    # ---- 3. 压缩（增量合并：旧摘要 + 新消息 → 单条新摘要，替换旧摘要） ----

    async def CompactMessagesAsync(
        self, messages: list[ContextMessage], targetTokens: int,
        oldSummary: ContextMessage | None = None,
    ) -> CompactionResult:
        """对 Session 消息执行增量 LLM 分级压缩。

        核心规则：
        1. 若传入 oldSummary（Session 级压缩摘要），将其与未压缩消息合并
        2. 合并后压缩为单条新摘要，旧摘要入 compactedIds 标记废弃
        3. 新摘要继承旧摘要的 summarizedFrom + 新压缩消息的 ID
        4. 若未传入 oldSummary，使用批量压缩产生单条摘要

        Args:
            messages: Session 中的 ContextMessage 列表。
            targetTokens: 目标 token 上限。
            oldSummary: Session 级已有压缩摘要（独立存储，不在 messages 中）。

        Returns:
            CompactionResult。
        """
        # 未压缩的非摘要消息
        uncompacted = [
            m for m in messages
            if not m.isCompacted and not m.summarizedFrom
        ]

        if oldSummary is not None:
            # ---- 增量压缩：旧摘要 + 未压缩消息 → 单条新摘要 ----
            toCompress = [oldSummary] + sorted(uncompacted, key=lambda m: m.turnIndex)
            estimated = self._tokenEstimator.EstimateMessages(toCompress)
            if estimated <= targetTokens:
                return CompactionResult(
                    messages=toCompress, compactedIds=[], newSummaryMessages=[]
                )

            # 强制批量压缩，确保只有 1 条输出
            result = await self._compactor.CompactBatchAsync(toCompress, targetTokens)

            # 继承旧摘要的 source IDs
            if result.newSummaryMessages:
                newSummary = result.newSummaryMessages[0]
                inheritedIds = list(oldSummary.summarizedFrom)
                # 用继承 ID 替换旧摘要自身的 ID
                newIds = [
                    mid for mid in newSummary.summarizedFrom
                    if mid != oldSummary.messageId
                ]
                newSummary.summarizedFrom = inheritedIds + newIds

            # 旧摘要 ID 也入 compactedIds
            allCompactedIds = [oldSummary.messageId] + result.compactedIds
            return CompactionResult(
                messages=result.messages,
                compactedIds=allCompactedIds,
                newSummaryMessages=result.newSummaryMessages,
            )
        else:
            # ---- 首次压缩：批量压缩产生单条摘要 ----
            assembled = self.AssembleMessages(messages)
            return await self._compactor.CompactBatchAsync(assembled, targetTokens)

    # ---- 属性 ----

    @property
    def Config(self) -> ContextConfig:
        return self._config

    def __repr__(self) -> str:
        return f"ContextLodManager(config={self._config!r})"
