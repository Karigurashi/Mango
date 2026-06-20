"""Agent 编排器 —— ReAct 主循环，对标 Claude Code Agent 调度机制。

继承 BaseAgent 的四维调用接口，将 BaseLLM + SessionComponent + ContextComponent +
HarnessComponent + registries 组装为完整的 ReAct Agent，驱动
Think → Act → Observe 循环。
"""

from __future__ import annotations

import asyncio
import time
from io import StringIO

from typing import AsyncIterator, Iterator, Optional

from common.const import ERole
from common.asyncUtil import RunAsyncGenerator
from common.cancellationToken import CancellationToken
from common.logger import Logger

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
from agent.component.logging.loggingComponent import LoggingComponent
from agent.component.eventPush.eventPushComponent import EventPushComponent

from agent.component.data.agentConfig import AgentConfig
from agent.component.data.dataComponent import DataComponent
from agent.component.data.eAgentState import EAgentState

from .core.baseAgent import BaseAgent
from .agentStreamEvent import AgentStreamEvent

from llm.baseLLM import BaseLLM
from llm.provider.chatMessage import ChatChunk, ToolCall


class Agent(BaseAgent):
    """ReAct Agent 主编排器。

    继承 BaseAgent，提供四维调用接口；同时将 BaseLLM / SessionComponent /
    ContextComponent / HarnessComponent 组装为完整的 ReAct 循环。

    """

    def __init__(
        self,
        llm: BaseLLM,
        config: AgentConfig | None = None,
    ) -> None:
        super().__init__()
        self._buildCompleted = False
        self._runLock: asyncio.Lock | None = None  # 惰性初始化，避免 Python 3.12+ 同步构造时无事件循环崩溃

        # ---- 挂载全部 Component ----
        self._dataComp = self.AddComponent(DataComponent)
        self._dataComp.llm = llm   

        if config is not None:
            self._dataComp.config = config
       
        self._llmComponent = self.AddComponent(LLMComponent)
        self._session = self.AddComponent(SessionComponent)
        self._ctxComp = self.AddComponent(ContextComponent)
        self._ruleComp = self.AddComponent(RuleComponent)
        self._skillComp = self.AddComponent(SkillComponent)
        self._mcpComp = self.AddComponent(McpComponent)
        self._toolComp = self.AddComponent(ToolComponent)
        self._harnessComp = self.AddComponent(HarnessComponent)
        self._loggingComp = self.AddComponent(LoggingComponent)
        self._eventPushComp = self.AddComponent(EventPushComponent)

        # ---- 统一初始化 ----
        self.InitAllComponents()

    # ---- 四维入口 ----

    async def RunStreamAsync(
        self,
        userMessage: str,
        cancellationToken: Optional[CancellationToken] = None,
    ) -> AsyncIterator[AgentStreamEvent]:
        """异步流式 ReAct 循环（StreamAsync），逐 chunk yield 文本增量。"""
        if self._runLock is None:
            self._runLock = asyncio.Lock()
        if not self._TryAcquireRunLock():
            self._EmitEvent(AgentStreamEvent.ErrorEvent("Agent is already running, concurrent re-entry is not allowed"))
            self._EmitStateChange(EAgentState.ERROR)
            return
        async with self._runLock:
            self._dataComp.state = EAgentState.THINKING
            self._EmitStateChange(EAgentState.THINKING)
            async for event in self.RunWithLifecycleAsync(
                self._RunReActCoreAsync(userMessage, cancellationToken, streaming=True)
            ):
                yield event

    async def RunInvokeAsync(
        self,
        userMessage: str,
        cancellationToken: Optional[CancellationToken] = None,
    ) -> AsyncIterator[AgentStreamEvent]:
        """异步非流式 ReAct 循环（InvokeAsync），整段返回文本。"""
        if self._runLock is None:
            self._runLock = asyncio.Lock()
        if not self._TryAcquireRunLock():
            self._EmitEvent(AgentStreamEvent.ErrorEvent("Agent is already running, concurrent re-entry is not allowed"))
            self._EmitStateChange(EAgentState.ERROR)
            return
        async with self._runLock:
            self._dataComp.state = EAgentState.THINKING
            self._EmitStateChange(EAgentState.THINKING)
            async for event in self.RunWithLifecycleAsync(
                self._RunReActCoreAsync(userMessage, cancellationToken, streaming=False)
            ):
                yield event

    def RunStream(
        self,
        userMessage: str,
        cancellationToken: Optional[CancellationToken] = None,
    ) -> Iterator[AgentStreamEvent]:
        """同步流式 ReAct 循环（Stream）。"""
        yield from RunAsyncGenerator(
            self.RunAsync(userMessage, cancellationToken),
            timeout=self._dataComp.config.runTimeout or None,
        )

    def RunInvoke(
        self,
        userMessage: str,
        cancellationToken: Optional[CancellationToken] = None,
    ) -> Iterator[AgentStreamEvent]:
        """同步非流式 ReAct 循环（Invoke）。"""
        yield from RunAsyncGenerator(
            self.RunInvokeAsync(userMessage, cancellationToken),
            timeout=self._dataComp.config.runTimeout or None,
        )

    # ---- 运行锁（非阻塞获取，消除 TOCTOU 竞态） ----

    def _TryAcquireRunLock(self) -> bool:
        """同步预检查：运行锁是否可获取。

        仅做 locked() 快速检查，实际获取由 RunAsync 内的 async with 保证。
        由于 Python asyncio 单线程协程模型，从 yield 到 async with 之间
        不会被其他协程抢占，因此不存在真正的 TOCTOU 竞态。
        """
        if self._runLock is None:
            return True
        return not self._runLock.locked()

    # ---- 生命周期保证 ----

    async def RunWithLifecycleAsync(
        self,
        coreAsyncIterator: AsyncIterator[AgentStreamEvent],
    ) -> AsyncIterator[AgentStreamEvent]:
        """生命周期保证模板方法：包装核心异步迭代器，确保 AfterTurnAsync 在所有路径执行。

        无论核心循环正常结束、抛异常、被取消还是超限，
        finally 中的 AfterTurnAsync 都会被调用，避免内存泄漏
        （已压缩消息未 Purge、外存文件未 Cleanup、会话摘要未持久化）。

        Args:
            coreAsyncIterator: 核心异步迭代器（如 _RunReActCoreAsync 的返回值）。

        Yields:
            核心迭代器产生的每个事件。
        """
        normalExit = False
        try:
            async for event in coreAsyncIterator:
                yield event
            normalExit = True
        finally:
            if self._ctxComp is not None:
                await self._ctxComp.AfterTurnAsync()
            if self._loggingComp is not None:
                self._loggingComp.OnAfterTurnAsync()
            if not normalExit:
                self._dataComp.state = EAgentState.ERROR

    # ---- 公共 ReAct 核心 ----

    async def _RunReActCoreAsync(
        self,
        userMessage: str,
        cancellationToken: Optional[CancellationToken],
        streaming: bool,
    ) -> AsyncIterator[AgentStreamEvent]:
        """ReAct 核心循环，驱动 Think → Act → Observe。

        生命周期保证由 RunWithLifecycleAsync 提供（AfterTurnAsync / ERROR 状态），
        此方法只负责核心 ReAct 逻辑，不处理 finally 清理。

        Args:
            userMessage: 用户消息。
            cancellationToken: 外部传入的取消令牌。
            streaming: True 使用 StreamAsync 逐 chunk 流式输出；
                       False 使用 InvokeAsync 整段返回。
        """
        # ---- 装填 LOD0 Context（仅初始化一次） ----
        if not self._buildCompleted:
            await self._harnessComp.BuildAsync()
            # ---- 绑定工具到 LLMComponent ----
            toolSpecs = self._toolComp.GetAllToolSpecs()
            if toolSpecs:
                self._llmComponent.BindTools(toolSpecs)
            self._buildCompleted = True

        # ---- 解析 @rule-name 手动触发 ----
        for rule in self._ruleComp.MatchManualInvoke(userMessage):
            self._ctxComp.Ingest(
                ERole.SYSTEM,
                rule.body,
                lodLevel=EContextLodLevel.SUMMARIZABLE,
            )

        # ---- Ingest USER 消息 ----
        self._ctxComp.Ingest(ERole.USER, userMessage, lodLevel=EContextLodLevel.SUMMARIZABLE)

        # ---- 结构化日志：Run 启动 ----
        if self._loggingComp is not None:
            self._loggingComp.LogRunStart(userMessage)
        runStartTime = time.monotonic()

        # ---- ReAct 循环 ----
        for turn in range(self._dataComp.config.maxTurns):
            self._EmitEvent(AgentStreamEvent.TurnStart(turn))

            # Assemble 本次 LLM 调用的消息列表
            chatMessages = await self._ctxComp.AssembleAsync()

            # LLM 调用（含指数退避重试）
            contentBuf = StringIO()
            toolCalls: list[ToolCall] | None = None
            llmStartTime = time.monotonic()
            lastChunkUsage = None

            try:
                if streaming:
                    chunkIter = self._llmComponent.StreamAsync(
                        chatMessages, cancellationToken=cancellationToken,
                    )
                else:
                    response = await self._llmComponent.InvokeAsync(
                        chatMessages, cancellationToken=cancellationToken,
                    )
                    chunkIter = self._SingleChunkAsyncIter(
                        ChatChunk(
                            content=response.content,
                            toolCalls=response.toolCalls,
                            usage=response.usage,
                        )
                    )
                async for chunk in chunkIter:
                    if chunk.content:
                        contentBuf.write(chunk.content)
                        self._EmitEvent(AgentStreamEvent.TextDelta(chunk.content, turn))

                    if chunk.toolCalls:
                        if toolCalls is None:
                            toolCalls = []
                        toolCalls.extend(chunk.toolCalls)

                    if chunk.usage is not None:
                        lastChunkUsage = chunk.usage

            except Exception as exc:
                llmDuration = time.monotonic() - llmStartTime
                self._dataComp.state = EAgentState.ERROR
                errorMsg = f"LLM call failed at turn {turn}: {exc}"
                self._ctxComp.Ingest(ERole.ASSISTANT, f"[Error: {errorMsg}]", lodLevel=EContextLodLevel.DISCARDABLE)
                if self._loggingComp is not None:
                    self._loggingComp.LogLLMCall(
                        turnIndex=turn, modelName=self._llmComponent.ModelName,
                        inputTokens=0, outputTokens=0,
                        duration=llmDuration, streaming=streaming, success=False,
                    )
                    self._loggingComp.LogRunEnd(
                        totalTurns=turn, totalDuration=time.monotonic() - runStartTime,
                        totalTokens=0, endState=EAgentState.ERROR.name,
                    )
                self._EmitEvent(AgentStreamEvent.ErrorEvent(errorMsg, turn))
                self._EmitStateChange(EAgentState.ERROR, turn)
                return

            # ---- 结构化日志：LLM 调用完成 ----
            llmDuration = time.monotonic() - llmStartTime
            if self._loggingComp is not None:
                inputTokens = lastChunkUsage.promptTokens if lastChunkUsage else 0
                outputTokens = lastChunkUsage.completionTokens if lastChunkUsage else 0
                self._loggingComp.LogLLMCall(
                    turnIndex=turn, modelName=self._llmComponent.ModelName,
                    inputTokens=inputTokens, outputTokens=outputTokens,
                    duration=llmDuration, streaming=streaming, success=True,
                )

            # 检查取消
            if cancellationToken is not None and cancellationToken.IsCancellationRequested:
                if self._loggingComp is not None:
                    self._loggingComp.LogRunEnd(
                        totalTurns=turn, totalDuration=time.monotonic() - runStartTime,
                        totalTokens=0, endState="CANCELLED",
                    )
                self._EmitEvent(AgentStreamEvent.ErrorEvent("Cancelled by user", turn))
                self._EmitStateChange(EAgentState.ERROR, turn)
                return

            # ---- 工具执行 ----
            if toolCalls:
                self._dataComp.state = EAgentState.ACTING
                self._EmitStateChange(EAgentState.ACTING, turn)

                toolStartTime = time.monotonic()
                # 工具执行异常隔离：单工具失败不中断本批，统一降级为 Fail 结果
                results: list[ToolResult] = []
                for tc in toolCalls:
                    try:
                        result = await self._toolComp.DispatchAsync(tc)
                    except Exception as exc:
                        Logger.Warning(
                            f"Tool '{tc.name}' raised unhandled exception at turn {turn}: {exc}"
                        )
                        result = ToolResult.Fail(
                            f"Tool execution error: {exc}",
                            toolName=tc.name,
                        )
                    results.append(result)
                batchDuration = time.monotonic() - toolStartTime

                # ---- 结构化日志：工具批量执行完成 ----
                if self._loggingComp is not None:
                    for tc, result in zip(toolCalls, results):
                        self._loggingComp.LogToolExecution(
                            turnIndex=turn, toolName=tc.name,
                            duration=batchDuration, success=result.success,
                            resultChars=len(result.ToLLMContent()) if result.ToLLMContent() else 0,
                        )

                # 先 Ingest 带 tool_calls 的 ASSISTANT 消息（LLM API 要求 ASSISTANT 在 TOOL 之前）
                # 必须携带 toolCalls，否则后续 TOOL 消息会被 OpenAI 视为孤儿而拒绝
                fullContent = contentBuf.getvalue()
                assistantContent = fullContent.strip() or "[Tool calls dispatched]"
                self._ctxComp.Ingest(
                    ERole.ASSISTANT,
                    assistantContent,
                    lodLevel=EContextLodLevel.SUMMARIZABLE,
                    toolCalls=toolCalls,
                )

                # 再 Ingest TOOL 结果
                for tc, result in zip(toolCalls, results):
                    self._EmitEvent(AgentStreamEvent.ToolStart(tc.name, tc.arguments, turn))
                    tool = self._toolComp.Get(tc.name)
                    lodLevel = (
                        tool.resultLodLevel
                        if tool is not None and tool.resultLodLevel is not None
                        else EContextLodLevel.EXTERNAL_ONLY
                    )
                    skipPersist = (
                        tool.skipPersist
                        if tool is not None
                        else False
                    )
                    # 工具返回时即判断落盘，Ingest 仅管上下文生命周期
                    rawContent = result.ToLLMContent()
                    ingestContent = self._ctxComp.PersistToolResult(
                        rawContent, skipPersist
                    )
                    # toolCallId 必须与发起的 ToolCall.id 匹配，OpenAI 据此关联工具回合
                    self._ctxComp.Ingest(
                        ERole.TOOL,
                        ingestContent,
                        lodLevel=lodLevel,
                        toolCallId=tc.id,
                    )
                    self._EmitEvent(AgentStreamEvent.ToolResultEvent(tc.name, result, turn))

                self._dataComp.state = EAgentState.THINKING
                continue

            # ---- 纯文本响应：本轮结束 ----
            fullContent = contentBuf.getvalue()
            self._ctxComp.Ingest(ERole.ASSISTANT, fullContent, lodLevel=EContextLodLevel.SUMMARIZABLE)
            break

        else:
            # maxTurns 耗尽 —— 视为异常终止
            errorMsg = f"Exceeded max turns ({self._dataComp.config.maxTurns})"
            self._dataComp.state = EAgentState.ERROR
            if self._loggingComp is not None:
                self._loggingComp.LogRunEnd(
                    totalTurns=self._dataComp.config.maxTurns,
                    totalDuration=time.monotonic() - runStartTime,
                    totalTokens=0, endState=EAgentState.ERROR.name,
                )
            self._EmitEvent(AgentStreamEvent.ErrorEvent(errorMsg))
            self._EmitStateChange(EAgentState.ERROR)
            self._EmitDone()
            return

        # ---- 回合收尾（正常路径） ----
        if self._dataComp.config.autoCompact:
            await self._ctxComp.CompactAsync()

        self._dataComp.state = EAgentState.FINISHED

        # ---- 结构化日志：Run 正常结束 ----
        if self._loggingComp is not None:
            sessionMetrics = self._loggingComp.GetSessionMetrics()
            self._loggingComp.LogRunEnd(
                totalTurns=sessionMetrics["totalTurns"],
                totalDuration=time.monotonic() - runStartTime,
                totalTokens=sessionMetrics["totalTokens"],
                endState=EAgentState.FINISHED.name,
            )

        self._EmitStateChange(EAgentState.FINISHED)
        self._EmitDone()

    def _EmitEvent(self, event: AgentStreamEvent) -> AgentStreamEvent:
        self._eventPushComp.Push(event)
        return event

    def _EmitStateChange(self, state: EAgentState, turnIndex: int = 0) -> AgentStreamEvent:
        ev = AgentStreamEvent.StateChange(state, turnIndex)
        self._eventPushComp.Push(ev)
        return ev

    def _EmitDone(self) -> AgentStreamEvent:
        ev = AgentStreamEvent.Done()
        self._eventPushComp.Push(ev)
        return ev

    # ---- LLM 重试 ----

    async def _SingleChunkAsyncIter(self, chunk: ChatChunk) -> AsyncIterator[ChatChunk]:
        """将单个 ChatChunk 包装为异步迭代器，与非流式 InvokeAsync 对齐调用模式。"""
        yield chunk

    # ---- 魔法方法 ----

    def __repr__(self) -> str:
        modelName = self._llmComponent.ModelName if self._llmComponent.llm else "<no model>"
        return (
            f"Agent(state={self._dataComp.state.name}, "
            f"model={modelName}, "
            f"session={self._session.sessionId[:8]}...)"
        )
