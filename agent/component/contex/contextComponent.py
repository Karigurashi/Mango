"""上下文引擎 —— 编排 Ingest → Assemble → Compact → AfterTurn 四阶段生命周期。

ContextComponent 不存储任何消息。只负责：
1. 摄入时构造 ContextMessage 并写入 SessionComponent
2. 组装时从 SessionComponent 读取、过滤、组织
3. 压缩时从 SessionComponent 读取、压缩、回写

作为 IComponent 可挂载到 BaseAgent，通过 OnInitialize 感知 Agent 上下文。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent.core.baseComponent import IComponent
from agent.component.session.sessionComponent import SessionComponent
from agent.component.data.dataComponent import DataComponent
from agent.component.data.agentConfig import AgentConfig
from common.const import ERole
from common.logger import Logger
from llm.provider.chatMessage import ChatMessage, ToolCall

from .contentStore import ContentStore
from .contextLodManager import ContextLodManager
from .contextMessage import ContextMessage
from .eContextLodLevel import EContextLodLevel
from llm.tokenEstimator import TokenEstimator

if TYPE_CHECKING:
    from agent.component.llm.llmComponent import LLMComponent


class ContextComponent(IComponent):
    """上下文引擎 —— SessionComponent 与 LLM 之间的调度器。

    不存储任何消息，消息的唯一归属地是 SessionComponent。

    四阶段生命周期：
    1. Ingest       —— 外部消息摄入：构造 ContextMessage → 写入 SessionComponent
    2. AssembleAsync —— 从 SessionComponent 组装消息列表（LOD 3 仅当轮注入，已压缩消息跳过）
    3. CompactAsync  —— token 超预算时触发压缩：组装 → LLM 摘要 → 回写 SessionComponent
    4. AfterTurnAsync —— 清理外存、持久化 SessionComponent

    Usage::

        engine = ContextComponent()
        messages = await engine.AssembleAsync()
        # ... 调用 AI ...
        await engine.AfterTurnAsync()
    """

    def __init__(self) -> None:
        self._session: SessionComponent | None = None
        self._llmComponent: LLMComponent | None = None
        self._config: AgentConfig = AgentConfig.Default()
        self._contentStore: ContentStore | None = None
        self._lodManager: ContextLodManager | None = None
        self._tokenEstimator: TokenEstimator | None = None  # 实例级隔离
        self._turnIndex = 0
        self._ingestedCount = 0
        self._estimatedTokens = 0
        self._lastColdOffloadTurn = -1  # 上次冷卸载的 turn，避免重复执行

    # ---- IComponent 生命周期 ----

    def OnInitialize(self, agent: BaseAgent) -> None:
        """挂载后初始化，自动注入依赖并从 DataComponent 获取配置。

        从 Agent 获取 SessionComponent、LLMComponent、DataComponent，
        使用 AgentConfig 创建 ContentStore 和 ContextLodManager。
        """
        from agent.component.llm.llmComponent import LLMComponent

        self._session = agent.GetComponent(SessionComponent)
        self._llmComponent = agent.GetComponent(LLMComponent)
        dataComp = agent.GetComponent(DataComponent)
        self._config = dataComp.config
        self._contentStore = ContentStore(
            self._config.storeDir,
            maxFileSize=self._config.storeMaxFileSize,
            maxTotalSize=self._config.storeMaxTotalSize,
        )
        # 获取 Agent 级独立 TokenEstimator 实例，多 Agent 并发互不干扰
        self._tokenEstimator = (
            self._llmComponent.TokenEstimatorInstance
            if self._llmComponent is not None
            else TokenEstimator()
        )
        self._lodManager = ContextLodManager(
            self._config, self._contentStore, self._llmComponent.llm,
            tokenEstimator=self._tokenEstimator,
        )

    def OnDestroy(self) -> None:
        """从 BaseAgent 卸载时回调。"""
        pass

    # ---- 四阶段 ----

    def Ingest(
        self,
        role: ERole,
        content: str,
        lodLevel: EContextLodLevel | None = None,
        persisted: bool = False,
        toolCalls: list[ToolCall] | None = None,
        toolCallId: str = "",
    ) -> ContextMessage:
        """摄入一条消息到 SessionComponent。

        lodLevel 不传时按 role 自动判定。工具结果的落盘+预览
        应在调用前由 PersistToolResult() 处理，Ingest 不关心落盘。

        Args:
            role: 消息角色（ERole 枚举）。
            content: 消息内容（工具结果应已经过 PersistToolResult 处理）。
            lodLevel: 外部显式指定 LOD，不传则按 role 自动计算。
            persisted: 内容是否已通过 PersistToolResult 落盘。
                       为 True 且 role=TOOL 时自动升级为 EXTERNAL_ONLY。
            toolCalls: ASSISTANT 消息发起的工具调用列表，回放时供 LLM
                       识别工具回合（OpenAI 要求 tool 消息前置 tool_calls）。
            toolCallId: TOOL 消息对应的工具调用 ID，必须与发起的
                        ToolCall.id 匹配，否则 OpenAI 拒绝该消息。

        Returns:
            创建并写入 SessionComponent 的 ContextMessage。
        """
        # USER 消息触发轮次递增（比 count//2 更准确）
        if role == ERole.USER:
            self._turnIndex += 1
        turnIndex = self._turnIndex

        # 外部未传入时按 role 自动判定 LOD
        if lodLevel is None:
            lodLevel = self._DefaultLodForRole(role)
            # 已落盘的工具结果自动升级为 EXTERNAL_ONLY（当轮注入、次轮丢弃）
            if persisted and role == ERole.TOOL:
                lodLevel = EContextLodLevel.EXTERNAL_ONLY

        contextMsg = ContextMessage.Create(
            chatMessage=ChatMessage(
                role=role,
                content=content,
                toolCalls=toolCalls,
                toolCallId=toolCallId,
            ),
            lodLevel=lodLevel,
            turnIndex=turnIndex,
        )

        # 工具结果：清理热尾窗口外的 LOD 2 旧消息
        if role == ERole.TOOL:
            self._OffloadColdLod2()

        self._session.Append(contextMsg)
        self._ingestedCount += 1
        return contextMsg

    def PersistToolResult(self, content: str, skipPersist: bool = False) -> str:
        """工具结果落盘+预览 —— 在 Ingest 前调用。

        当结果超过 persistCharThreshold 且未跳过落盘时：
        1. 完整内容写入 ContentStore
        2. 返回 <persisted-output> 预览文本

        未触发落盘时原样返回 content。

        Args:
            content: 工具返回的原始内容。
            skipPersist: 跳过落盘（如 read_file 源文件已在磁盘）。

        Returns:
            应注入上下文的内容（原始内容或预览文本）。
        """
        if skipPersist or not self._config.enablePersist:
            return content

        if len(content) <= self._config.persistCharThreshold:
            return content

        storePath = self._contentStore.Store(content)
        return self._contentStore.BuildPersistedPreview(
            storePath, content, self._config.persistPreviewChars
        )

    def _OffloadColdLod2(self) -> None:
        """将热尾窗口外的 LOD 2 消息标记为冷卸载，释放上下文 token。

        对标 Claude Code 的 Microcompaction：旧工具结果不再占用上下文，
        AI 需要时可重新执行工具获取。不写入 ContentStore，
        避免对已有磁盘文件（如 read_file 结果）重复落盘。

        使用 isAgedOut 标记位代替直接篡改 content，原始内容不丢失，
        组装时通过 CreateAgedOutProjection() 生成占位投影。

        性能优化：使用 self._turnIndex 代替全量扫描，每轮仅执行一次。
        """
        # 每轮最多执行一次，避免同一轮内多次 TOOL Ingest 重复扫描
        if self._turnIndex <= self._lastColdOffloadTurn:
            return
        self._lastColdOffloadTurn = self._turnIndex

        messages = self._session.messages  # 直接引用，不拷贝
        if not messages:
            return

        keepRecent = self._config.keepRecentTurns
        if keepRecent <= 0:
            return

        threshold = self._turnIndex - keepRecent + 1

        for msg in messages:
            if msg.lodLevel != EContextLodLevel.DISCARDABLE:
                continue
            if msg.turnIndex >= threshold:
                continue
            # 已标记冷卸载的跳过
            if msg.isAgedOut:
                continue
            byteSize = len(msg.content.encode("utf-8")) if msg.content else 0
            msg.MarkAgedOut(byteSize)

    @staticmethod
    def _DefaultLodForRole(role: ERole) -> EContextLodLevel:
        """按 role 提供默认 LOD 等级。"""
        if role == ERole.SYSTEM:
            return EContextLodLevel.RESIDENT
        if role == ERole.TOOL:
            return EContextLodLevel.DISCARDABLE
        if role in (ERole.USER, ERole.ASSISTANT):
            return EContextLodLevel.SUMMARIZABLE
        return EContextLodLevel.DISCARDABLE

    async def AssembleAsync(self, tokenBudget: int | None = None) -> list[ContextMessage]:
        """从 SessionComponent 组装本次 AI 调用的消息列表。

        组装规则：
        1. 若 SessionComponent 存在压缩摘要 → [摘要] + (turnIndex > 压缩覆盖范围的后续消息)
        2. 无压缩摘要 → 全部未压缩消息
        3. 若消息超预算，自动触发持久化 CompactAsync 后重新组装。

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

        # 超预算时触发持久化压缩，避免每轮重复消耗 LLM 调用
        estimated = self._tokenEstimator.EstimateMessages(projected)

        # 超预算时触发持久化压缩
        if estimated > budget:
            await self.CompactAsync(force=True)
            # 压缩后重新组装
            messages = self._session.GetAll()
            compressed = self._session.CompressedSummary
            if compressed is not None:
                upToTurn = self._session.CompressedUpToTurnIndex
                tail = [m for m in messages if m.turnIndex > upToTurn]
                projected = self._lodManager.AssembleMessages(tail)
                projected.insert(0, compressed)
            else:
                projected = self._lodManager.AssembleMessages(messages)
            estimated = self._tokenEstimator.EstimateMessages(projected)

        # 压缩后仍超预算（如 RESIDENT/SUMMARIZABLE 本身过大）：硬兜底，
        # 从最旧的可丢弃消息（DISCARDABLE/EXTERNAL_ONLY）开始剔除，避免直接超长报错。
        # 被剔除的孤儿工具结果由 Agent 层 _SanitizeToolMessages 统一对齐。
        if estimated > budget:
            projected, estimated = self._TrimToBudget(projected, budget)

        self._estimatedTokens = estimated
        return projected

    def _TrimToBudget(
        self,
        messages: list[ContextMessage], budget: int
    ) -> tuple[list[ContextMessage], int]:
        """将消息列表裁剪至预算内，仅剔除可丢弃消息，保留不可丢弃内容。

        从最旧的可丢弃（CanDiscard）消息开始移除，直到满足预算或只剩
        不可丢弃消息。返回新列表与裁剪后估算，不修改入参与 Session。

        使用两遍扫描代替反复 pop(i)，将 O(n²) 降为 O(n)：
        - 第一遍：计算可丢弃消息的前缀 token 和
        - 第二遍：从尾部保留足够的可丢弃消息以满足预算

        Args:
            messages: 待裁剪的消息列表。
            budget: token 预算上限。

        Returns:
            (裁剪后的消息列表, 裁剪后 token 估算)。
        """
        estimated = self._tokenEstimator.EstimateMessages(messages)
        if estimated <= budget:
            return messages, estimated

        # 计算不可丢弃消息的 token 总和
        nonDiscardableTokens = 0
        for msg in messages:
            if not msg.lodLevel.CanDiscard():
                nonDiscardableTokens += self._tokenEstimator.EstimateMessage(msg)

        # 如果仅不可丢弃消息已超预算，无需再裁剪
        if nonDiscardableTokens > budget:
            result = [m for m in messages if not m.lodLevel.CanDiscard()]
            Logger.Warning(
                f"Context still over budget after trimming: "
                f"{nonDiscardableTokens} > {budget} (only non-discardable messages remain)"
            )
            return result, nonDiscardableTokens

        # 从最旧可丢弃消息开始剔除，直到满足预算
        result: list[ContextMessage] = []
        runningTokens = nonDiscardableTokens
        # 先收集可丢弃消息的 token 信息
        discardableWithTokens = []
        for msg in messages:
            if msg.lodLevel.CanDiscard():
                discardableWithTokens.append((msg, self._tokenEstimator.EstimateMessage(msg)))

        # 从尾部（最新）保留可丢弃消息，直到加上不可丢弃的总量 <= budget
        keptDiscardable: list[ContextMessage] = []
        keptTokens = 0
        for msg, msgTokens in reversed(discardableWithTokens):
            if runningTokens + keptTokens + msgTokens <= budget:
                keptDiscardable.insert(0, msg)
                keptTokens += msgTokens
            else:
                break

        # 合并不可丢弃 + 保留的可丢弃，按原始顺序
        discardableSet = set(id(m) for m in keptDiscardable)
        result = [m for m in messages if not m.lodLevel.CanDiscard() or id(m) in discardableSet]
        finalTokens = nonDiscardableTokens + keptTokens

        return result, finalTokens

    async def CompactAsync(self, force: bool = False) -> int:
        """触发 LLM 分级压缩，结果写入 SessionComponent 独立压缩摘要字段。

        流程：
        1. 从 SessionComponent 读取并组装
        2. 若超阈值（或强制），执行 LLM 压缩
        3. 被压缩的原始消息标记 isCompacted
        4. 新生成的摘要写入 SessionComponent._compressedSummary（独立存储）
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

        # 回写 SessionComponent：标记被压缩的原始消息
        for msgId in result.compactedIds:
            self._session.MarkCompacted(msgId)

        # 计算实际被压缩消息的最大 turnIndex（避免覆盖范围过大）
        compactedTurns = [
            m.turnIndex for m in messages if m.messageId in set(result.compactedIds)
        ]
        compactedMaxTurn = max(compactedTurns) if compactedTurns else -1

        # 回写 Session：设置唯一的压缩摘要（独立存储，不追加到 messages）
        if result.newSummaryMessages:
            newSummary = result.newSummaryMessages[0]
            self._session.SetCompressedSummary(newSummary, compactedMaxTurn)
        else:
            # 无新摘要但仍有消息被标记压缩（如仅丢弃 LOD2），
            # 若已有旧摘要则更新其覆盖范围
            if self._session.CompressedSummary is not None and compactedMaxTurn > self._session.CompressedUpToTurnIndex:
                self._session.SetCompressedSummary(
                    self._session.CompressedSummary, compactedMaxTurn
                )

        afterTokens = self._tokenEstimator.EstimateMessages(result.messages)
        return beforeTokens - afterTokens

    async def AfterTurnAsync(self) -> None:
        """回合结束后收尾。

        执行：
        1. 清理过期外存文件（storeMaxAge<=0 时跳过）
        2. 清理已压缩消息，释放内存
        3. 持久化 SessionComponent 到 Memory
        """
        if self._config.storeMaxAge > 0:
            import time
            cutoff = time.time() - self._config.storeMaxAge
            self._contentStore.Cleanup(olderThan=cutoff)
        self._session.PurgeCompacted()
        self._session.SaveToMemory()

    # ---- 属性 ----

    @property
    def EstimatedTokens(self) -> int:
        """上次 AssembleAsync 后的 token 估算数。"""
        return self._estimatedTokens

    @property
    def Session(self) -> SessionComponent:
        return self._session

    @property
    def Config(self) -> AgentConfig:
        return self._config

    @property
    def LodManager(self) -> ContextLodManager:
        return self._lodManager

    def __repr__(self) -> str:
        return (
            f"ContextComponent(session={self._session.sessionId[:8]}..., "
            f"ingested={self._ingestedCount})"
        )
