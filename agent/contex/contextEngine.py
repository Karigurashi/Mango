"""上下文引擎 —— 编排 Ingest → Assemble → Compact → AfterTurn 四阶段生命周期。

ContextEngine 不存储任何消息。只负责：
1. 摄入时构造 ContextMessage 并写入 Session
2. 组装时从 Session 读取、过滤、组织
3. 压缩时从 Session 读取、压缩、回写
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from common.const import ERole
from llm.provider.chatMessage import ChatMessage

from .contentStore import ContentStore
from .contextConfig import ContextConfig
from .contextLodManager import ContextLodManager
from .contextMessage import ContextMessage
from .eContextLodLevel import EContextLodLevel
from .session import Session
from .tokenEstimator import TokenEstimator

if TYPE_CHECKING:
    from llm.baseLLM import BaseLLM


class ContextEngine:
    """上下文引擎 —— Session 与 LLM 之间的调度器。

    不存储任何消息，消息的唯一归属地是 Session。

    四阶段生命周期：
    1. Ingest       —— 外部消息摄入：构造 ContextMessage → 写入 Session
    2. AssembleAsync —— 从 Session 组装消息列表（LOD 3 不注入，已压缩消息跳过）
    3. CompactAsync  —— token 超预算时触发压缩：组装 → LLM 摘要 → 回写 Session
    4. AfterTurnAsync —— 清理外存、持久化 Session

    Usage::

        engine = ContextEngine(session, config, llm=compactProvider)
        messages = await engine.AssembleAsync()
        # ... 调用 AI ...
        await engine.AfterTurnAsync()
    """

    def __init__(
        self,
        session: Session,
        config: ContextConfig | None = None,
        contentStore: ContentStore | None = None,
        tokenEstimator: TokenEstimator | None = None,
        llm: BaseLLM | None = None,
    ) -> None:
        self._session = session
        self._config = config or ContextConfig()
        self._contentStore = contentStore or ContentStore(self._config.storeDir)
        self._tokenEstimator = tokenEstimator or TokenEstimator()
        self._lodManager = ContextLodManager(
            self._config, self._contentStore, self._tokenEstimator, llm
        )
        self._ingestedCount = 0
        self._estimatedTokens = 0

    # ---- 四阶段 ----

    def Ingest(
        self,
        role: ERole,
        content: str,
        metadata: dict | None = None,
        lodLevel: EContextLodLevel | None = None,
    ) -> ContextMessage:
        """摄入一条消息到 Session。

        lodLevel 不传时按 role + metadata 自动判定，工具结果额外经
        LodManager 按大小阈值覆盖。

        Args:
            role: 消息角色（ERole 枚举）。
            content: 消息内容。
            metadata: 扩展元数据（isThinking、isDecision 等）。
            lodLevel: 外部可显式指定 LOD，不传则自动计算。

        Returns:
            创建并写入 Session 的 ContextMessage。
        """
        turnIndex = self._ingestedCount // 2

        # 外部未传入时自动判定 LOD
        if lodLevel is None:
            lodLevel = self._ClassifyLod(role, metadata or {})

        contextMsg = ContextMessage.Create(
            chatMessage=ChatMessage(role=role, content=content),
            lodLevel=lodLevel,
            turnIndex=turnIndex,
            metadata=metadata,
        )

        # 工具结果按大小阈值二次判定；超大结果外存并替换为路径引用
        if role == ERole.TOOL:
            self._ApplyToolResultLod(contextMsg, content, metadata)

        self._session.Append(contextMsg)
        self._ingestedCount += 1
        return contextMsg

    def _ApplyToolResultLod(
        self,
        contextMsg: ContextMessage,
        content: str,
        metadata: dict | None,
    ) -> None:
        """判定工具结果 LOD；超大内容写入 ContentStore 并注入路径引用。"""
        toolLod = self._lodManager._ClassifyToolResult(content)
        if toolLod != EContextLodLevel.EXTERNAL_ONLY:
            contextMsg.lodLevel = toolLod
            return

        meta = dict(metadata or {})
        storedPath = self._contentStore.Store(content, metadata=meta)
        byteSize = len(content.encode("utf-8"))
        summary = self._contentStore.GetSummary(storedPath)
        contextMsg.content = self._contentStore.BuildPathReference(
            storedPath, byteSize, summary
        )
        contextMsg.lodLevel = EContextLodLevel.DISCARDABLE
        meta["externalPath"] = storedPath
        meta["externalOnly"] = True
        contextMsg.metadata = meta

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

    async def AssembleAsync(self, tokenBudget: int | None = None) -> list[ContextMessage]:
        """从 Session 组装本次 AI 调用的消息列表。

        纯读取操作，不回写 Session。组装规则：
        1. 若 Session 存在压缩摘要 → [摘要] + (turnIndex > 压缩覆盖范围的后续消息)
        2. 无压缩摘要 → 全部未压缩消息
        3. 若消息超预算，执行瞬态压缩（仅用于本次视图，不持久化）。

        可通过 EstimatedTokens 属性获取上次组装的 token 估算。

        Args:
            tokenBudget: token 预算，不传则使用 config 中配置的有效预算。

        Returns:
            组装好的 ContextMessage 列表。
        """
        budget = tokenBudget if tokenBudget is not None else self._config.effectiveBudget

        messages = self._session.GetAll()
        compressed = self._session.CompressedSummary
        if compressed is not None:
            upToTurn = self._session.CompressedUpToTurnIndex
            tail = [m for m in messages if m.turnIndex > upToTurn]
            projected = self._lodManager.AssembleMessages(tail)
            projected.insert(0, compressed)
        else:
            projected = self._lodManager.AssembleMessages(messages)

        # 超预算时瞬态压缩（仅用于本次视图，不持久化）
        estimated = self._tokenEstimator.EstimateMessages(projected)
        if estimated > budget:
            result = await self._lodManager._compactor.CompactBatchAsync(projected, budget)
            projected = result.messages
            estimated = self._tokenEstimator.EstimateMessages(projected)

        self._estimatedTokens = estimated
        return projected

    async def CompactAsync(self, force: bool = False) -> int:
        """触发 LLM 分级压缩，结果写入 Session 独立压缩摘要字段。

        流程：
        1. 从 Session 读取并组装
        2. 若超阈值（或强制），执行 LLM 压缩
        3. 被压缩的原始消息标记 isCompacted
        4. 新生成的摘要写入 Session._compressedSummary（独立存储）
        5. 记录压缩覆盖的最大 turnIndex

        Args:
            force: 是否强制压缩（忽略阈值）。

        Returns:
            压缩释放的 token 数（0 表示未触发压缩）。
        """
        if not force and not self._config.autoCompact:
            return 0

        budget = self._config.effectiveBudget
        messages = self._session.GetAll()

        assembled = self._lodManager.AssembleMessages(messages)
        estimated = self._tokenEstimator.EstimateMessages(assembled)

        threshold = int(budget * self._config.compactThreshold)
        if not force and estimated <= threshold:
            return 0

        beforeTokens = estimated
        result = await self._lodManager.CompactMessagesAsync(
            messages, threshold,
            oldSummary=self._session.CompressedSummary,
        )

        # 回写 Session：标记被压缩的原始消息
        for msgId in result.compactedIds:
            self._session.MarkCompacted(msgId)

        # 回写 Session：设置唯一的压缩摘要（独立存储，不追加到 messages）
        if result.newSummaryMessages:
            newSummary = result.newSummaryMessages[0]
            maxTurn = max((m.turnIndex for m in messages), default=-1)
            self._session.SetCompressedSummary(newSummary, maxTurn)
        else:
            # 无新摘要但仍有消息被标记压缩（如仅丢弃 LOD2），
            # 若已有旧摘要则更新其覆盖范围
            maxTurn = max((m.turnIndex for m in messages), default=-1)
            if self._session.CompressedSummary is not None:
                self._session.SetCompressedSummary(
                    self._session.CompressedSummary, maxTurn
                )

        afterTokens = self._tokenEstimator.EstimateMessages(result.messages)
        return beforeTokens - afterTokens

    async def AfterTurnAsync(self) -> None:
        """回合结束后收尾。

        执行：
        1. 清理过期外存文件
        2. 持久化 Session 到 Memory
        """
        cutoff = None
        if self._config.storeMaxAge > 0:
            import time
            cutoff = time.time() - self._config.storeMaxAge
        self._contentStore.Cleanup(olderThan=cutoff)
        self._session.SaveToMemory()

    # ---- 属性 ----

    @property
    def EstimatedTokens(self) -> int:
        """上次 AssembleAsync 后的 token 估算数。"""
        return self._estimatedTokens

    @property
    def Session(self) -> Session:
        return self._session

    @property
    def Config(self) -> ContextConfig:
        return self._config

    @property
    def LodManager(self) -> ContextLodManager:
        return self._lodManager

    def __repr__(self) -> str:
        return (
            f"ContextEngine(session={self._session.sessionId[:8]}..., "
            f"ingested={self._ingestedCount})"
        )
