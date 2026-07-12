"""上下文引擎 —— 编排 Ingest → Assemble → Compact → AfterTurn 四阶段生命周期。

ContextComponent 不存储任何消息。只负责：
1. 摄入时构造 ContextMessage 并写入 SessionComponent
2. 组装时从 SessionComponent 读取、过滤、组织
3. 压缩时从 SessionComponent 读取、压缩、回写

作为 IComponent 可挂载到 BaseAgent，通过 OnInitialize 感知 Agent 上下文。
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from agent.core.baseComponent import IComponent
from agent.component.data.agentConfig import AgentConfig
from agent.component.data.dataComponent import DataComponent
from agent.component.eventBus.agentStreamEvent import AgentStreamEvent
from agent.component.eventBus.eventBusComponent import EventBusComponent
from agent.component.llm.llmComponent import LLMComponent
from agent.component.session.sessionComponent import SessionComponent
from agent.component.store.storeComponent import StoreComponent
from common.const import ERole
from llm.provider.chatMessage import ChatMessage, ToolCall

from .contextCompactor import ContextCompactor
from .contextMessage import ContextMessage
from .eContextLodLevel import EContextLodLevel

if TYPE_CHECKING:
    from agent.core.baseAgent import BaseAgent


class ContextComponent(IComponent):
    """上下文引擎 —— SessionComponent 与 LLM 之间的调度器。

    不存储任何消息，消息的唯一归属地是 SessionComponent。

    四阶段生命周期：
    1. Ingest       —— 外部消息摄入：构造 ContextMessage → 写入 SessionComponent
    2. AssembleAsync —— 从 SessionComponent 组装消息列表（LOD 3 仅当轮注入，已压缩消息跳过）
    3. CompactAsync  —— token 超预算时触发压缩：组装 → LLM 摘要 → 回写 SessionComponent
    4. AfterTurnAsync —— 清除 LOD3 过期消息

    Usage::

        engine = ContextComponent()
        messages = await engine.AssembleAsync()
        # ... 调用 AI ...
        await engine.AfterTurnAsync()
    """

    def __init__(self) -> None:
        self._sessionComponent: SessionComponent | None = None
        self._llmComponent: LLMComponent | None = None
        self._eventBusComponent: EventBusComponent | None = None
        self._storeComp: StoreComponent | None = None

        self._config: AgentConfig | None = None  # OnInitialize 时从 DataComponent 注入
        self._compactor: ContextCompactor | None = None
        self._chatMessages: list[ChatMessage] = []  # AssembleAsync 复用列表，每次 clear() 避免 GC
        # 并发保护：CompactAsync 与 Ingest 共享 Session 消息列表，
        # 通过 asyncio.Lock 串行化压缩流程，避免并发压缩重入造成状态错乱。
        self._lock = asyncio.Lock()

    # ---- IComponent 生命周期 ----

    def OnInitialize(self, agent: BaseAgent) -> None:
        """挂载后初始化，自动注入依赖并从 DataComponent 获取配置。

        从 Agent 获取 SessionComponent、LLMComponent、StoreComponent、DataComponent，
        使用 AgentConfig 和 StoreComponent 创建 ContextCompactor。
        """
        self._sessionComponent = agent.GetComponent(SessionComponent)
        self._llmComponent = agent.GetComponent(LLMComponent)
        self._eventBusComponent = agent.GetComponent(EventBusComponent)
        dataComp = agent.GetComponent(DataComponent)
        self._config = dataComp.config

        self._storeComp = agent.GetComponent(StoreComponent)

        self._compactor = ContextCompactor(
            self._config, self._llmComponent.llm,
            estimateTokens=self._llmComponent.EstimateTokens,
            storeComp=self._storeComp,
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
            toolCalls: ASSISTANT 消息发起的工具调用列表，回放时供 LLM
                       识别工具回合（OpenAI 要求 tool 消息前置 tool_calls）。
            toolCallId: TOOL 消息对应的工具调用 ID，必须与发起的
                        ToolCall.id 匹配，否则 OpenAI 拒绝该消息。

        Returns:
            创建并写入 SessionComponent 的 ContextMessage。
        """
        # 外部未传入时按 role 自动判定 LOD
        if lodLevel is None:
            lodLevel = self.DefaultLodForRole(role)

        contextMsg = ContextMessage.Create(
            chatMessage=ChatMessage(
                role=role,
                content=content,
                toolCalls=toolCalls,
                toolCallId=toolCallId,
            ),
            lodLevel=lodLevel,
        )

        self._sessionComponent.Append(contextMsg)
        return contextMsg

    def PersistToolResult(self, content: str, skipPersist: bool = False) -> str:
        """工具结果落盘+预览 —— 在 Ingest 前调用。

        超阈值时统一截断，避免大内容膨胀上下文：
        - enablePersist 且未 skipPersist：写入 ContentStore 并返回预览
        - skipPersist（源文件已在磁盘）或 enablePersist=False：截断为预览文本

        Args:
            content: 工具返回的原始内容。
            skipPersist: 跳过落盘（如 read_file 源文件已在磁盘）。

        Returns:
            应注入上下文的内容（原始内容或预览文本）。
        """
        threshold = self._config.persistCharThreshold
        previewChars = self._config.persistPreviewChars

        if len(content) <= threshold:
            return content

        if not skipPersist and self._config.enablePersist:
            storePath = self._storeComp.Store(content)
            return self._storeComp.BuildPersistedPreview(
                storePath, content, previewChars
            )

        # 超阈值但无法落盘：统一截断
        return f"[TRUNC {len(content)}→{previewChars}] {content[:previewChars]}... read_file startLine/endLine"

    @staticmethod
    def DefaultLodForRole(role: ERole) -> EContextLodLevel:
        """按 role 提供默认 LOD 等级。"""
        if role == ERole.SYSTEM:
            return EContextLodLevel.RESIDENT
        if role == ERole.TOOL:
            return EContextLodLevel.DISCARDABLE
        if role in (ERole.USER, ERole.ASSISTANT):
            return EContextLodLevel.SUMMARIZABLE
        return EContextLodLevel.DISCARDABLE

    # ---- 组装 ----

    def AutoColdOffloadIfNeeded(self) -> None:
        """每轮用户对话前自动检测宽限期并执行冷卸载。

        若 autoColdOffload 关闭或最后一条消息距当前时间未超
        coldOffloadGraceSeconds，则跳过。否则对 Session 中
        DISCARDABLE 消息原地冷卸载（零 LLM 成本）。

        冷卸载原地修改消息内容后，增量估算基准（lastPromptTokens）
        不再有效，下一轮 AssembleAsync 将从 LLMComponent 重新取值。
        """
        if not self._config.autoColdOffload:
            return

        messages = self._sessionComponent.conversationMessages
        if self._compactor.IsWithinGracePeriod(messages):
            return

        self._compactor.OffloadColdLod2InPlace(messages, 0)

    async def AssembleAsync(self, tokenBudget: int | None = None) -> list[ChatMessage]:
        """从 Session 组装本次 AI 调用的消息列表。

        Session 数据即上下文数据，直接读取无需视图过滤。
        若消息超预算，自动触发 CompactAsync 后重新组装。

        Args:
            tokenBudget: token 预算，不传则使用 config 中配置的有效预算。

        Returns:
            组装好的 ChatMessage 列表。
        """
        budget = tokenBudget if tokenBudget is not None else self._config.effectiveBudget
        residentMessages = self._sessionComponent.residentMessages
        conversationMessages = self._sessionComponent.conversationMessages
        estimated = self._llmComponent.LastPromptTokens

        # 超预算时触发持久化压缩（CompactAsync 内部已清理孤儿 tool_calls）
        if estimated >= budget:
            await self.CompactAsync(force=True)

        self._chatMessages.clear()
        for cm in residentMessages:
            self._chatMessages.append(cm.chatMessage)
        for cm in conversationMessages:
            self._chatMessages.append(cm.chatMessage)

        # 标记 Prompt Caching：连续 RESIDENT 前缀末尾打 cacheControl
        self._ApplyCacheControl(residentMessages)

        return self._chatMessages

    @staticmethod
    def _ApplyCacheControl(residentMessages: list[ContextMessage]) -> None:
        """在连续 RESIDENT 前缀末尾打 cacheControl 标记。

        Anthropic Prompt Caching 规则：cache_control 标记的消息及之前
        所有内容被服务端缓存为 KV-Cache。仅在 stable prefix（RESIDENT）
        末尾标记，后续动态消息不标记以避免前缀变化导致缓存全部失效。

        标记直接修改 ChatMessage.cacheControl，不创建新对象。
        """
        if residentMessages:
            residentMessages[-1].chatMessage.cacheControl = True

    async def CompactAsync(self, force: bool = False) -> int:
        """统一容量管理入口，委托 ContextCompactor.ManageCapacityAsync。

        两优先级流程（从低成本到高成本，逐级早退）：
        1. 冷 DISCARDABLE → ContentStore 落盘 + 路径引用（零 LLM 成本）
        2. SUMMARIZABLE → LLM 批量摘要

        压缩后直接 ApplyCompactionResult 写入 Session，摘要作为 turnIndex == -1 的
        普通消息存储在 messages 列表中，不再单独存储。

        Args:
            force: 是否强制执行（忽略阈值检查）。

        Returns:
            压缩释放的 token 数（0 表示未触发处理）。
        """
        async with self._lock:
            budget = self._config.effectiveBudget
            threshold = int(budget * self._config.compactThreshold)
            messages = self._sessionComponent.conversationMessages
            assembledTokens = self._llmComponent.EstimateTokens(messages)
            beforeTokens = assembledTokens

            if not force and beforeTokens <= threshold:
                return 0

            result = await self._compactor.ManageCapacityAsync(
                messages=messages,
                tokenBudget=threshold,
                preEstimatedTokens=assembledTokens,
                force=force,
            )

            if result.compactedCount == 0 and not result.newSummaryMessages:
                # 仅冷卸载（原地内容替换）发生，无需回写
                afterTokens = self._llmComponent.EstimateTokens(result.messages)
                tokenSaved = max(beforeTokens - afterTokens, 0)
                if tokenSaved > 0 and self._eventBusComponent is not None:
                    self._eventBusComponent.Push(AgentStreamEvent.Compaction(
                        tokenSaved=tokenSaved,
                        compactedCount=0,
                    ))
                return tokenSaved

            # 使用压缩产物替换 Session 消息列表（保留 LOD0）
            self._sessionComponent.ApplyCompactionResult(result.messages)

            # 压缩可能产生孤儿 tool_calls（如冷卸载部分工具结果后关联
            # ASSISTANT 仍幸存，或硬截断丢弃 DISCARDABLE 后对应
            # SUMMARIZABLE 仍保留），必须在回写后立即清理。
            self._sessionComponent.FixOrphanedToolCalls()

            afterTokens = self._llmComponent.EstimateTokens(result.messages)
            tokenSaved = max(beforeTokens - afterTokens, 0)

            # 推送压缩事件
            if tokenSaved > 0 and self._eventBusComponent is not None:
                compactedCount = result.compactedCount
                self._eventBusComponent.Push(AgentStreamEvent.Compaction(
                    tokenSaved=tokenSaved,
                    compactedCount=compactedCount,
                ))

            return tokenSaved

    async def AfterTurnAsync(self) -> None:
        """回合结束后收尾。

        清理顺序：
        1. 清除所有 LOD3(EXTERNAL_ONLY) 消息
           — LOD3 语义为"当轮注入、次轮丢弃"，每轮结束统一清除

        外存文件由 ContentStore 内部的 LRU 策略自动淘汰。
        """
        self._sessionComponent.ClearLod3()

    def __repr__(self) -> str:
        sessionId = self._sessionComponent.sessionId if self._sessionComponent else "None"
        return f"ContextComponent(session={sessionId})"
