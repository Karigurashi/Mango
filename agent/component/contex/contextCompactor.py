"""容量管理器 —— 统一冷卸载、LLM 摘要为单一流程。

ManageCapacityAsync 是上下文模块唯一的容量管理入口：
- 估算总 token，未超预算直接放行；
- 超预算按"零成本落盘 → LLM 摘要"两优先级释放 token，
  直到满足预算或所有可释放策略耗尽。
"""

from __future__ import annotations

import asyncio
import re
import time

from typing import Callable, NamedTuple, Optional, TYPE_CHECKING

from common.cancellationToken import CancellationToken
from common.const import ERole
from common.logger import Logger
from llm.provider.chatMessage import ChatMessage
from llm.llmRequestParams import LLMRequestParams

from agent.component.data.agentConfig import AgentConfig, DEFAULT_BATCH_SUMMARY_PROMPT
from .contextMessage import ContextMessage
from .eContextLodLevel import EContextLodLevel

if TYPE_CHECKING:
    from llm.baseLLM import BaseLLM
    from agent.component.store.storeComponent import StoreComponent

# ---- 预编译 regex（_FormatCompactSummary 使用）----
_RE_ANALYSIS_BLOCK = re.compile(r"<analysis>[\s\S]*?</analysis>", re.IGNORECASE)
_RE_RESIDUAL_TAGS = re.compile(r"</?analysis>|<example>|</example>", re.IGNORECASE)
_RE_MULTI_BLANK = re.compile(r"\n\n+")


class CompactionResult(NamedTuple):
    """容量管理操作的完整结果。

    Attributes:
        messages: 处理后的消息列表（原地修改 + 摘要替换 + 丢弃后的最终视图）。
        compactedCount: 被丢弃或摘要化的消息数量（不含冷卸载，冷卸载是原地占位）。
        newSummaryMessages: 新生成的摘要消息列表（供回写 Session）。
    """

    messages: list[ContextMessage]
    compactedCount: int
    newSummaryMessages: list[ContextMessage] = []


class ContextCompactor:
    """统一容量管理器：按优先级释放 token 直到满足预算。

    优先级（从低成本到高成本）：
    1. 冷 DISCARDABLE（热尾窗口外）→ ContentStore 落盘 + 路径引用（零 LLM 成本）
    2. SUMMARIZABLE → LLM 批量摘要（保留语义，有成本）
    3. 硬截断 → 从旧到新丢弃非 RESIDENT（兜底，确保满足预算）

    LOD0/RESIDENT 任何情况下都不可触碰；BaseLLM 不可用时优先级 2 退化到截断兜底。
    """

    # 压缩专用 LLM 调用超时（秒），防止模型响应极慢导致压缩流程卡死
    _COMPACTION_TIMEOUT: float = 60.0

    def __init__(
        self,
        config: AgentConfig,
        llm: BaseLLM | None = None,
        estimateTokens: Callable[[list[ContextMessage]], int] | None = None,
        storeComp: StoreComponent | None = None,
    ) -> None:
        self._config = config
        self._llm = llm
        self._estimateTokens = estimateTokens or (lambda msgs: 0)
        self._storeComp = storeComp

    # ---- 统一容量管理入口 ----

    async def ManageCapacityAsync(
        self,
        messages: list[ContextMessage],
        tokenBudget: int,
        cancellationToken: Optional[CancellationToken] = None,
        preEstimatedTokens: int | None = None,
        force: bool = False,
    ) -> CompactionResult:
        """按三优先级释放 token，直到满足预算或仅剩 RESIDENT。

        Args:
            messages: 待管理的消息列表（已由调用方组装、过滤，含旧摘要）。
            tokenBudget: 目标 token 上限。
            cancellationToken: 协作式取消令牌。
            preEstimatedTokens: 调用方已估算的 token 数，避免重复全量估算。
            force: 强制执行压缩，忽略 tokenBudget 阈值检查。

        Returns:
            CompactionResult，messages 反映最终视图，compactedCount 为被丢弃/摘要化的消息数量。
        """
        estimated = preEstimatedTokens if preEstimatedTokens is not None else self._estimateTokens(messages)

        # 1. 未超预算且非强制 → 直接返回，零开销（延迟拷贝，避免无谓的 list(messages)）
        if not force and estimated <= tokenBudget:
            return CompactionResult(
                messages=messages, compactedCount=0
            )

        result: list[ContextMessage] = list(messages)

        compactedCount = 0
        newSummaryMessages: list[ContextMessage] = []

        # 2. 第一优先级：冷 LOD2 落盘为路径引用（零 LLM 成本）
        estimated = self.OffloadColdLod2InPlace(result, estimated)

        # 3. 第二优先级：SUMMARIZABLE → LLM 摘要（超预算或强制时执行）
        if force or estimated > tokenBudget:
            compactedCount = len(result)
            result, estimated, summaryMsg = await self._SummarizeAsync(
                result, cancellationToken
            )
            if summaryMsg is not None:
                newSummaryMessages.append(summaryMsg)

        # 4. 第三优先级：硬截断兜底（前两级仍超预算时执行）
        if estimated > tokenBudget:
            Logger.Warning(
                f"ManageCapacity unable to meet budget after cold-offload + summary: "
                f"{estimated} > {tokenBudget}. Falling back to hard truncation."
            )
            truncatedIds, result, estimated = self._HardTruncateInPlace(result, tokenBudget, estimated)
            compactedCount += len(truncatedIds)

        return CompactionResult(
            messages=result,
            compactedCount=compactedCount,
            newSummaryMessages=newSummaryMessages,
        )

    # ---- 优先级 1：冷 LOD2 原地占位 ----

    def IsWithinGracePeriod(self, messages: list[ContextMessage]) -> bool:
        """宽限期保护：最后一条消息距当前时间未超 coldOffloadGraceSeconds。

        保持前缀一致以保护 DeepSeek 等 Provider 的 Prompt Cache 命中率。
        仅在自动冷卸载触发时调用，压缩触发路径不检查宽限期。
        """
        if not messages:
            return False
        graceSeconds = self._config.coldOffloadGraceSeconds
        if graceSeconds <= 0:
            return False
        lastMsgTime = messages[-1].createdAt
        if lastMsgTime <= 0:
            return False
        return (time.time() - lastMsgTime) < graceSeconds

    def OffloadColdLod2InPlace(
        self,
        messages: list[ContextMessage],
        currentTokens: int,
    ) -> int:
        """保留最近 keepRecentTurns 条 DISCARDABLE 消息，其余冷卸载 + token 重估。

        对标 Claude Code 的 Microcompaction，零 LLM 成本，
        ContentStore 不可用时退化到 [aged:XKB] 占位。
        """
        keepRecent = self._config.keepRecentTurns
        if keepRecent <= 0 or not messages:
            return currentTokens

        # 从后往前遍历，保留最新 keepRecent 条 DISCARDABLE，其余冷卸载
        toKeep = keepRecent
        for msg in reversed(messages):
            if msg.lodLevel == EContextLodLevel.DISCARDABLE and not msg.isAgedOut:
                if toKeep > 0:
                    toKeep -= 1
                else:
                    self._ApplyColdOffload(msg)

        if toKeep == keepRecent:
            return currentTokens

        # 内容变更后必须重算 token，确保估算与实际一致
        return self._estimateTokens(messages)

    def _ApplyColdOffload(self, msg: ContextMessage) -> None:
        """将单条消息内容落盘并替换为路径引用占位文本（幂等）。"""
        if msg.isAgedOut:
            return
        currentContent = msg.content
        if self._storeComp is not None and currentContent and len(currentContent) > 100:
            storePath = self._storeComp.Store(currentContent)
            msg.content = f"[aged in {storePath}]"
        else:
            byteSize = len(currentContent.encode("utf-8")) if currentContent else 0
            msg.content = f"[aged:{byteSize / 1024:.1f}KB]"
        msg.isAgedOut = True

    # ---- 优先级 2：LOD1 LLM 摘要 + 保留N次工具调用 ----

    async def _SummarizeAsync(
        self,
        messages: list[ContextMessage],
        cancellationToken: Optional[CancellationToken],
    ) -> tuple[list[ContextMessage], int, ContextMessage | None]:
        """对 SUMMARIZABLE 消息批量调用 LLM 生成单条摘要，替换原始内容。DISCARDABLE（工具结果）不参与摘要，仅走冷落盘。

        Returns:
            (新消息列表, 新 token 估算, 新摘要消息或 None)。
        """
        # 热尾窗口内仍保留的 DISCARDABLE（工具结果）所在 ASSISTANT (tool_calls)
        # 必须保留，否则 TOOL 消息会孤儿化导致 API 400 错误
        preservedToolCallIds: set[str] = {
            m.chatMessage.toolCallId for m in messages
            if m.lodLevel == EContextLodLevel.DISCARDABLE and not m.isAgedOut
            and m.chatMessage.toolCallId
        }

        toSummarize: list[ContextMessage] = [
            m for m in messages
            if m.lodLevel == EContextLodLevel.SUMMARIZABLE
            and not (
                m.role == ERole.ASSISTANT
                and m.chatMessage.toolCalls
                and any(tc.id in preservedToolCallIds for tc in m.chatMessage.toolCalls)
            )
        ]

        if not toSummarize:
            return messages, self._estimateTokens(messages), None

        combinedText = "\n---\n".join(
            f"[{m.role}] {m.content}" for m in toSummarize
        )
        rawSummary = await self._SummarizeBatchAsync(combinedText, cancellationToken)
        summary = self._FormatCompactSummary(rawSummary)

        summaryMsg = ContextMessage(
            chatMessage=ChatMessage(
                role=ERole.SYSTEM,
                content=f"<compactHistory>\n{summary}\n</compactHistory>",
            ),
            lodLevel=EContextLodLevel.SUMMARIZABLE,
            isSummary=True,
        )

        # 剔除已摘要的消息 + 已冷卸载的工具（isAgedOut）
        compactedSet = {m.messageId for m in toSummarize}
        survivors = [
            m for m in messages
            if m.messageId not in compactedSet and not m.isAgedOut
        ]

        # 若保留了最近工具结果，插入分隔说明
        hasRecentTools = any(
            m.lodLevel == EContextLodLevel.DISCARDABLE for m in survivors
        )
        if hasRecentTools:
            separator = ContextMessage(
                chatMessage=ChatMessage(
                    role=ERole.SYSTEM,
                    content="Recent tool call results preserved below:",
                ),
                lodLevel=EContextLodLevel.SUMMARIZABLE,
                isSummary=True,
            )
            newMessages = [summaryMsg, separator] + survivors
        else:
            newMessages = [summaryMsg] + survivors
        newEstimated = self._estimateTokens(newMessages)
        return newMessages, newEstimated, summaryMsg

    # ---- LLM 摘要核心 ----

    async def _SummarizeBatchAsync(
        self,
        combinedText: str,
        cancellationToken: Optional[CancellationToken] = None,
    ) -> str:
        """对批量文本调用 LLM 生成摘要，LLM 不可用时退化到截断。"""
        if self._llm is None:
            return self._TruncateText(
                combinedText, self._config.batchSummaryMaxTokens * 4
            )

        prompt = (
            self._config.compactionPrompt
            or DEFAULT_BATCH_SUMMARY_PROMPT
        )
        userContent = f"{prompt}\n\n<conversation>\n{combinedText}\n</conversation>"

        try:
            response = await asyncio.wait_for(
                self._llm.InvokeAsync(
                    [ChatMessage.User(userContent)],
                    requestParams=LLMRequestParams(
                        temperature=0.2,
                        maxTokens=self._config.batchSummaryMaxTokens,
                    ),
                ),
                timeout=self._COMPACTION_TIMEOUT,
            )
            return response.content.strip()
        except (asyncio.TimeoutError, Exception) as exc:
            Logger.Warning(
                f"LLM compaction failed, falling back to truncation: {exc}"
            )
            return self._TruncateText(
                combinedText, self._config.batchSummaryMaxTokens * 4
            )

    # ---- 摘要格式化（对标 Claude Code formatCompactSummary）----

    @staticmethod
    def _FormatCompactSummary(summary: str) -> str:
        """剥离 <analysis> 草稿区，保留 <summary> 正文，对标 Claude Code。

        <analysis> 是 LLM 的组织思路草稿，不含增量信息价值，
        剥离后节省上下文 token。
        """
        formatted = _RE_ANALYSIS_BLOCK.sub("", summary)
        formatted = _RE_RESIDUAL_TAGS.sub("", formatted)
        formatted = _RE_MULTI_BLANK.sub("\n\n", formatted)
        return formatted.strip()

    # ---- 截断兜底 ----

    @staticmethod
    def _TruncateText(text: str, maxChars: int) -> str:
        """截断文本到指定字符数，保留首尾关键信息。"""
        if len(text) <= maxChars:
            return text
        half = maxChars // 2
        if half < 50:
            return text[:maxChars] + "…"
        return text[:half] + "\n…[truncated]…\n" + text[-half:]

    # ---- 优先级 3：硬截断兜底 ----

    def _HardTruncateInPlace(
        self,
        messages: list[ContextMessage],
        tokenBudget: int,
        currentTokens: int,
    ) -> tuple[list[int], list[ContextMessage], int]:
        """分级丢弃非 RESIDENT 消息，直到满足预算或无更多可丢弃项。

        前两级策略（冷卸载 + LLM 摘要）无法满足预算时的最后兜底。
        丢弃优先级（从先到后，信息价值递增）：
        1. DISCARDABLE（工具结果，信息密度最低）
        2. SUMMARIZABLE 非摘要（已参与过摘要的原始消息）
        3. 压缩摘要（turnIndex=-1，LLM 成本的唯一产物，最后丢弃）
        RESIDENT 不可触碰。

        Returns:
            (被丢弃的消息 ID 列表, 截断后消息列表, 新 token 估算)。
        """
        if not messages:
            return [], messages, currentTokens

        truncatedIds: list[int] = []

        # ---- Pass 1: 从旧到新丢弃 DISCARDABLE ----
        currentTokens = self._DropByPredicate(
            messages, currentTokens, tokenBudget, truncatedIds,
            lambda m: m.lodLevel == EContextLodLevel.DISCARDABLE,
        )
        if currentTokens <= tokenBudget:
            return truncatedIds, messages, currentTokens

        # ---- Pass 2: 从旧到新丢弃 SUMMARIZABLE（不含摘要）----
        currentTokens = self._DropByPredicate(
            messages, currentTokens, tokenBudget, truncatedIds,
            lambda m: (m.lodLevel == EContextLodLevel.SUMMARIZABLE
                       and not m.isSummary),
        )
        if currentTokens <= tokenBudget:
            return truncatedIds, messages, currentTokens

        # ---- Pass 3: 最后丢弃压缩摘要自身 ----
        currentTokens = self._DropByPredicate(
            messages, currentTokens, tokenBudget, truncatedIds,
            lambda m: (m.lodLevel == EContextLodLevel.SUMMARIZABLE
                       and m.isSummary),
        )

        return truncatedIds, messages, currentTokens

    def _DropByPredicate(
        self,
        messages: list[ContextMessage],
        currentTokens: int,
        tokenBudget: int,
        truncatedIds: list[int],
        predicate,
    ) -> int:
        """从前往后遍历，丢弃满足 predicate 的消息直到满足预算或无可匹配项。

        原地修改 messages 列表，不产生中间分配。

        Returns:
            丢弃后的 token 估算值。
        """
        if not messages:
            return currentTokens
        i = 0
        while i < len(messages) and currentTokens > tokenBudget:
            if predicate(messages[i]):
                truncatedIds.append(messages[i].messageId)
                messages.pop(i)
                currentTokens = self._estimateTokens(messages)
            else:
                i += 1
        return currentTokens

    @staticmethod
    def __repr__(self) -> str:
        hasLlm = self._llm is not None
        return (
            f"ContextCompactor(keepRecent={self._config.keepRecentTurns}, "
            f"llm={hasLlm})"
        )
