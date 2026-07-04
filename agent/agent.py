"""Agent 编排器 —— ReAct 主循环，对标 Claude Code Agent 调度机制。

继承 BaseAgent，将 BaseLLM + SessionComponent + ContextComponent +
HarnessComponent + registries 组装为完整的 ReAct Agent，驱动
Think → Act → Observe 循环。
"""

from __future__ import annotations

import asyncio
from typing import Optional

from common.const import ERole
from common.cancellationToken import CancellationToken

from agent.component.contex.contextComponent import ContextComponent
from agent.component.contex.eContextLodLevel import EContextLodLevel
from agent.component.session.sessionComponent import SessionComponent
from agent.component.harness.harnessComponent import HarnessComponent
from agent.component.llm.llmComponent import LLMComponent
from agent.component.rule.ruleComponent import RuleComponent
from agent.component.skill.skillComponent import SkillComponent
from agent.component.mcp.mcpComponent import McpComponent
from agent.component.tool.toolComponent import ToolComponent
from agent.component.tool.toolResult import ToolResult

from agent.component.eventBus.eventBusComponent import EventBusComponent

from agent.component.data.agentConfig import AgentConfig
from agent.component.data.dataComponent import DataComponent
from agent.component.data.eAgentState import EAgentState

from .core.baseAgent import BaseAgent
from .component.eventBus.agentStreamEvent import AgentStreamEvent

from llm.baseLLM import BaseLLM
from llm.provider.chatMessage import ToolCall


class Agent(BaseAgent):
    """ReAct Agent 主编排器。

    继承 BaseAgent，将 BaseLLM / SessionComponent /
    ContextComponent / HarnessComponent 组装为完整的 ReAct 循环。

    """

    def __init__(
        self,
        llm: BaseLLM,
        config: AgentConfig | None = None,
    ) -> None:
        super().__init__()
        self._runLock: asyncio.Lock | None = None  # 惰性初始化，避免 Python 3.12+ 同步构造时无事件循环崩溃
        self._lastContent: str = ""                 # 最近一轮 LLM 产出的文本内容，供 _ExecuteToolCallsAsync 使用

        # ---- 挂载全部 Component（DataComponent 需预注入 LLM，其余即用即取）----
        self._dataComp = self.AddComponent(DataComponent)
        self._dataComp.llm = llm

        if config is not None:
            self._dataComp.config = config

        self._eventBusComp = self.GetComponent(EventBusComponent)
        self._llmComponent = self.GetComponent(LLMComponent)
        self._session = self.GetComponent(SessionComponent)
        self._ctxComp = self.GetComponent(ContextComponent)
        self._ruleComp = self.GetComponent(RuleComponent)
        self._skillComp = self.GetComponent(SkillComponent)
        self._mcpComp = self.GetComponent(McpComponent)
        self._toolComp = self.GetComponent(ToolComponent)
        self._harnessComp = self.GetComponent(HarnessComponent)

    @property
    def agentId(self) -> int:
        return self._dataComp.agentId

    @property
    def agentName(self) -> str:
        return self._dataComp.llm.modelName

    async def RunStreamAsync(
        self,
        userMessage: str,
        cancellationToken: Optional[CancellationToken] = None,
    ) -> None:
        """异步流式 ReAct 循环。事件通过 EventBusComponent 推送。"""
        await self._RunGuardedAsync(userMessage, cancellationToken, stream=True)

    async def RunAsync(
        self,
        userMessage: str,
        cancellationToken: Optional[CancellationToken] = None,
    ) -> None:
        """异步非流式 ReAct 循环。事件通过 EventBusComponent 推送。"""
        await self._RunGuardedAsync(userMessage, cancellationToken, stream=False)

    async def _RunGuardedAsync(
        self,
        userMessage: str,
        cancellationToken: Optional[CancellationToken],
        stream: bool,
    ) -> None:
        """统一入口：锁保护 + 生命周期包装。

        无论核心逻辑正常结束、抛异常、被取消还是超限，
        finally 中的 AfterTurnAsync 都会被调用，避免内存泄漏
        （已压缩消息未 Purge、外存文件未 Cleanup）。
        """
        if self._runLock is None:
            self._runLock = asyncio.Lock()
        if self._runLock.locked():
            self._EmitEvent(AgentStreamEvent.ErrorEvent("Agent is already running, concurrent re-entry is not allowed"))
            return
        async with self._runLock:
            normalExit = False
            try:
                await self._RunReActCoreAsync(userMessage, cancellationToken, stream=stream)
                normalExit = True
            except Exception as exc:
                import traceback
                self._EmitEvent(AgentStreamEvent.ErrorEvent(f"{type(exc).__name__}: {exc}"))
                traceback.print_exc()
                raise
            finally:
                await self._ctxComp.AfterTurnAsync()
                if not normalExit:
                    self._EmitStateChange(EAgentState.ERROR)
                    self._EmitDone()

    # ---- ReAct 核心骨架 ----

    async def _RunReActCoreAsync(
        self,
        userMessage: str,
        cancellationToken: Optional[CancellationToken],
        stream: bool = True,
    ) -> None:
        """ReAct 核心循环骨架，通过 stream 参数组合流式/非流式单轮执行。

        Args:
            userMessage: 用户消息。
            cancellationToken: 外部传入的取消令牌。
            stream: True 使用流式调用，False 使用非流式调用。
        """
        """构建 Harness、匹配规则、摄入用户消息。"""
        await self._harnessComp.BuildAsync()
        self._ctxComp.AutoColdOffloadIfNeeded()
        self._ctxComp.Ingest(ERole.USER, userMessage, lodLevel=EContextLodLevel.SUMMARIZABLE)

        maxTurns = self._dataComp.config.maxTurns
        turn = 0
        while maxTurns == -1 or turn < maxTurns:
            self._EmitEvent(AgentStreamEvent.TurnStart(turn))
            chatMessages = await self._ctxComp.AssembleAsync()

            if stream:
                toolCalls, isError = await self._RunTurnStreamAsync(turn, chatMessages, cancellationToken)
            else:
                toolCalls, isError = await self._RunTurnNonStreamAsync(turn, chatMessages, cancellationToken)

            if isError:
                return
            if toolCalls is None:
                break
            await self._ExecuteToolCallsAsync(turn, toolCalls)
            turn += 1
        else:
            if maxTurns != -1:
                self._HandleMaxTurnsExceeded()
                return

        self._FinishRunNormalAsync()

    # ---- Turn Helper ----

    def _HandleTurnError(self, turn: int, exc: Exception) -> tuple[None, bool]:
        """统一的 LLM 调用异常处理：记录错误到上下文、推送 ErrorEvent、返回 (None, True)。"""
        errorMsg = f"LLM call failed at turn {turn}: {exc}"
        self._ctxComp.Ingest(ERole.ASSISTANT, f"[Error: {errorMsg}]", lodLevel=EContextLodLevel.DISCARDABLE)
        self._EmitEvent(AgentStreamEvent.ErrorEvent(errorMsg, turn))
        self._EmitStateChange(EAgentState.ERROR, turn)
        return None, True

    def _IsCancelled(self, cancellationToken: Optional[CancellationToken], turn: int) -> bool:
        """检查取消令牌，若已取消则推送 ErrorEvent 并返回 True。"""
        if cancellationToken is not None and cancellationToken.IsCancellationRequested:
            self._EmitEvent(AgentStreamEvent.ErrorEvent("Cancelled by user", turn))
            self._EmitStateChange(EAgentState.ERROR, turn)
            return True
        return False

    # ---- 流式单轮 ----

    async def _RunTurnStreamAsync(
        self,
        turn: int,
        chatMessages,
        cancellationToken: Optional[CancellationToken],
    ) -> tuple[Optional[list[ToolCall]], bool]:
        """流式执行单轮 LLM 调用。

        Returns:
            (toolCalls, isError)
            - toolCalls=None 表示纯文本响应（本轮结束）。
            - isError=True 表示 LLM 调用失败或被取消，调用方应终止循环。
        """
        self._EmitStateChange(EAgentState.THINKING, turn)

        try:
            result = await self._llmComponent.StreamAsync(
                chatMessages, turnIndex=turn, cancellationToken=cancellationToken,
            )
        except Exception as exc:
            return self._HandleTurnError(turn, exc)

        if self._IsCancelled(cancellationToken, turn):
            return None, True

        self._lastContent = result.content

        # 纯文本响应：直接摄入 ASSISTANT（有工具时由 _ExecuteToolCallsAsync 负责摄入）
        if not result.toolCalls:
            self._ctxComp.Ingest(
                ERole.ASSISTANT, result.content,
                lodLevel=EContextLodLevel.SUMMARIZABLE,
            )

        return result.toolCalls, False

    # ---- 非流式单轮 ----

    async def _RunTurnNonStreamAsync(
        self,
        turn: int,
        chatMessages,
        cancellationToken: Optional[CancellationToken],
    ) -> tuple[Optional[list[ToolCall]], bool]:
        """非流式执行单轮 LLM 调用。

        Returns:
            (toolCalls, isError)
            - toolCalls=None 表示纯文本响应（本轮结束）。
            - isError=True 表示 LLM 调用失败或被取消，调用方应终止循环。
        """
        self._EmitStateChange(EAgentState.THINKING, turn)

        try:
            result = await self._llmComponent.InvokeAsync(
                chatMessages, turnIndex=turn, cancellationToken=cancellationToken,
            )
        except Exception as exc:
            return self._HandleTurnError(turn, exc)

        if self._IsCancelled(cancellationToken, turn):
            return None, True

        self._lastContent = result.content

        if not result.toolCalls:
            self._ctxComp.Ingest(
                ERole.ASSISTANT, result.content,
                lodLevel=EContextLodLevel.SUMMARIZABLE,
            )

        return result.toolCalls, False

    # ---- 工具执行 ----

    async def _ExecuteToolCallsAsync(
        self,
        turn: int,
        toolCalls: list[ToolCall],
    ) -> None:
        """执行工具调用、推送工具事件、摄入工具结果到上下文。"""
        self._EmitStateChange(EAgentState.ACTING, turn)

        for tc in toolCalls:
            self._EmitEvent(AgentStreamEvent.ToolStart(tc.name, tc.arguments, turn))
        results = await self._toolComp.DispatchBatchAsync(toolCalls)
        for tc, result in zip(toolCalls, results):
            self._EmitEvent(AgentStreamEvent.ToolResultEvent(tc.name, result, turn))

        # Ingest ASSISTANT（空 content 合法：LLM 可仅返回 toolCalls）
        self._ctxComp.Ingest(
            ERole.ASSISTANT,
            self._lastContent,
            lodLevel=EContextLodLevel.SUMMARIZABLE,
            toolCalls=toolCalls,
        )

        # Ingest TOOL 结果
        for tc, result in zip(toolCalls, results):
            tool = self._toolComp.Get(tc.name)
            lodLevel = (
                tool.resultLodLevel
                if tool is not None and tool.resultLodLevel is not None
                else EContextLodLevel.DISCARDABLE
            )
            skipPersist = tool.skipPersist if tool is not None else False
            rawContent = result.ToLLMContent()
            ingestContent = self._ctxComp.PersistToolResult(rawContent, skipPersist)
            self._ctxComp.Ingest(
                ERole.TOOL,
                ingestContent,
                lodLevel=lodLevel,
                toolCallId=tc.id,
            )

    # ---- 终止处理 ----

    def _HandleMaxTurnsExceeded(self) -> None:
        """maxTurns 耗尽，推送 ERROR 并终止。"""
        errorMsg = f"Exceeded max turns ({self._dataComp.config.maxTurns})"
        self._EmitEvent(AgentStreamEvent.ErrorEvent(errorMsg))
        self._EmitStateChange(EAgentState.ERROR)
        self._EmitDone()

    def _FinishRunNormalAsync(self) -> None:
        """正常结束：推送 FINISHED 状态（上下文压缩已在 AssembleAsync 中按需触发）。"""
        self._EmitStateChange(EAgentState.FINISHED)
        self._EmitDone()

    def _EmitEvent(self, event: AgentStreamEvent) -> None:
        self._eventBusComp.Push(event)

    def _EmitStateChange(self, state: EAgentState, turnIndex: int = 0) -> None:
        self._dataComp.state = state
        self._EmitEvent(AgentStreamEvent.StateChange(state, turnIndex))

    def _EmitDone(self) -> None:
        self._EmitEvent(AgentStreamEvent.Done())

    # ---- 魔法方法 ----

    def __repr__(self) -> str:
        modelName = self._llmComponent.modelName if self._llmComponent.llm else "<no model>"
        return (
            f"Agent(state={self._dataComp.state.name}, "
            f"model={modelName}, "
            f"session={self._session.sessionId})"
        )
