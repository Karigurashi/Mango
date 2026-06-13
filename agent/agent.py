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
from common.llmError import LLMError
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
from agent.component.logging.loggingComponent import LoggingComponent

from agent.component.data.agentConfig import AgentConfig
from agent.component.data.dataComponent import DataComponent
from agent.component.data.eAgentState import EAgentState

from .core.baseAgent import BaseAgent
from .agentStreamEvent import AgentStreamEvent, EAgentStreamEventType

from llm.baseLLM import BaseLLM
from llm.provider.chatMessage import ChatChunk, ChatMessage, ToolCall


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

        # ---- 统一初始化 ----
        self.InitAllComponents()


    # ---- Agent 属性 ----

    @property
    def State(self) -> EAgentState:
        return self._dataComp.state

    # ---- 四维入口 ----

    async def RunAsync(
        self,
        userMessage: str,
        cancellationToken: Optional[CancellationToken] = None,
    ) -> AsyncIterator[AgentStreamEvent]:
        """异步流式 ReAct 循环（StreamAsync），逐 chunk yield 文本增量。"""
        if self._runLock is None:
            self._runLock = asyncio.Lock()
        if not self._TryAcquireRunLock():
            yield AgentStreamEvent.ErrorEvent("Agent is already running, concurrent re-entry is not allowed")
            yield AgentStreamEvent.StateChange(EAgentState.ERROR)
            return
        async with self._runLock:
            self._dataComp.state = EAgentState.THINKING
            yield AgentStreamEvent.StateChange(EAgentState.THINKING)
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
            yield AgentStreamEvent.ErrorEvent("Agent is already running, concurrent re-entry is not allowed")
            yield AgentStreamEvent.StateChange(EAgentState.ERROR)
            return
        async with self._runLock:
            self._dataComp.state = EAgentState.THINKING
            yield AgentStreamEvent.StateChange(EAgentState.THINKING)
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

    # ---- 公共 ReAct 核心 ----

    async def _RunReActCoreAsync(
        self,
        userMessage: str,
        cancellationToken: Optional[CancellationToken],
        streaming: bool,
    ) -> AsyncIterator[AgentStreamEvent]:
        """ReAct 核心循环，驱动 Think → Act → Observe。

        生命周期保证由 BaseAgent.RunWithLifecycleAsync 提供（AfterTurnAsync / ERROR 状态），
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
            yield AgentStreamEvent.TurnStart(turn)

            # Assemble 本次 LLM 调用的消息列表
            contextMessages = await self._ctxComp.AssembleAsync()
            chatMessages = self._SanitizeToolMessages(contextMessages)

            # LLM 调用（含指数退避重试）
            contentBuf = StringIO()
            toolCalls: list[ToolCall] | None = None
            llmStartTime = time.monotonic()
            lastChunkUsage = None

            try:
                async for chunk in self._CallWithRetryAsync(
                    chatMessages, turn, cancellationToken,
                    streaming=streaming,
                ):
                    if chunk.content:
                        contentBuf.write(chunk.content)
                        yield AgentStreamEvent.TextDelta(chunk.content, turn)

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
                yield AgentStreamEvent.ErrorEvent(errorMsg, turn)
                yield AgentStreamEvent.StateChange(EAgentState.ERROR, turn)
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
                yield AgentStreamEvent.ErrorEvent("Cancelled by user", turn)
                yield AgentStreamEvent.StateChange(EAgentState.ERROR, turn)
                return

            # ---- 工具执行 ----
            if toolCalls:
                self._dataComp.state = EAgentState.ACTING
                yield AgentStreamEvent.StateChange(EAgentState.ACTING, turn)

                toolStartTime = time.monotonic()
                results = await self._toolComp.DispatchBatchAsync(toolCalls)
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
                    yield AgentStreamEvent.ToolStart(tc.name, tc.arguments, turn)
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
                    yield AgentStreamEvent.ToolResultEvent(tc.name, result, turn)

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
            yield AgentStreamEvent.ErrorEvent(errorMsg)
            yield AgentStreamEvent.StateChange(EAgentState.ERROR)
            yield AgentStreamEvent.Done()
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

        yield AgentStreamEvent.StateChange(EAgentState.FINISHED)
        yield AgentStreamEvent.Done()

    # ---- LLM 重试 ----

    async def _CallWithRetryAsync(
        self,
        chatMessages: list[ChatMessage],
        turn: int,
        cancellationToken: Optional[CancellationToken],
        streaming: bool = True,
    ) -> AsyncIterator[ChatChunk]:
        """带指数退避重试的 LLM 调用。
    
        根据 streaming 参数选择 StreamAsync（流式）或 InvokeAsync（非流式）。
        仅对可重试错误（429 限流、5xx 服务端错误）触发重试，
        取消信号、客户端错误（4xx 非 429）、超时不重试。
    
        重试延迟公式: min(retryBaseDelay * 2^attempt, retryMaxDelay)，
        并在等待期间轮询取消令牌。
    
        Args:
            chatMessages: 格式化的消息列表。
            turn: 当前推理轮次（仅用于日志）。
            cancellationToken: 取消令牌。
            streaming: True 使用 StreamAsync；False 使用 InvokeAsync。
    
        Yields:
            ChatChunk 流式增量。
    
        Raises:
            LLMError: 所有重试耗尽后仍失败时抛出。
        """
        maxRetries = self._dataComp.config.maxRetries
        baseDelay = self._dataComp.config.retryBaseDelay
        maxDelay = self._dataComp.config.retryMaxDelay
    
        lastException: Exception | None = None
    
        for attempt in range(maxRetries + 1):
            try:
                if streaming:
                    async for chunk in self._llmComponent.StreamAsync(
                        chatMessages,
                        cancellationToken=cancellationToken,
                    ):
                        yield chunk
                else:
                    response = await self._llmComponent.InvokeAsync(
                        chatMessages,
                        cancellationToken=cancellationToken,
                    )
                    yield ChatChunk(content=response.content, toolCalls=response.toolCalls)
                return  # 成功，退出重试循环

            except LLMError as exc:
                lastException = exc
                if not self._IsRetryable(exc):
                    raise

            except asyncio.CancelledError:
                raise

            except (asyncio.TimeoutError, ConnectionError, OSError) as exc:
                # 仅网络/IO 层异常可重试，编程错误（AttributeError 等）必须立即暴露
                lastException = exc

            # 最后一轮不再等待
            if attempt >= maxRetries:
                break

            # 检查取消
            if cancellationToken is not None and cancellationToken.IsCancellationRequested:
                raise LLMError("LLM call cancelled by user during retry backoff")

            delay = min(baseDelay * (2 ** attempt), maxDelay)
            Logger.Warning(
                f"LLM call failed at turn {turn}, attempt {attempt + 1}/{maxRetries + 1}, "
                f"retrying in {delay:.1f}s: {lastException}"
            )
            await asyncio.sleep(delay)

            # 等待后再次检查取消
            if cancellationToken is not None and cancellationToken.IsCancellationRequested:
                raise LLMError("LLM call cancelled by user during retry backoff")

        raise LLMError(
            f"LLM call exhausted all {maxRetries + 1} retry attempts at turn {turn}: {lastException}"
        )

    @staticmethod
    def _SanitizeToolMessages(contextMessages: list) -> list[ChatMessage]:
        """净化工具回合消息，剔除孤儿 tool_calls 与孤儿 TOOL 结果。

        上下文 LOD 生命周期不对称（assistant 的 tool_calls 为 SUMMARIZABLE 长期保留，
        而工具结果为 EXTERNAL_ONLY 次轮丢弃）会导致跨轮出现：
        - assistant 携带 tool_calls 但对应 TOOL 结果已被丢弃（孤儿调用）；
        - TOOL 结果无任何 assistant 引用（孤儿结果）。
        二者都会被 OpenAI 以 400 拒绝。此方法在组装后、发送前做一次对齐：
        仅保留"调用 ID 同时存在 assistant 发起记录与 TOOL 结果"的工具回合，
        其余 tool_calls 被剥离（保留文本），孤儿 TOOL 结果被丢弃。

        不修改 Session 中存储的原始 ChatMessage，必要时构造新实例。

        Args:
            contextMessages: AssembleAsync 组装后的 ContextMessage 列表。

        Returns:
            可安全发送给 LLM 的 ChatMessage 列表。
        """
        presentToolResultIds: set[str] = set()
        for cm in contextMessages:
            msg = cm.chatMessage
            if msg.role == ERole.TOOL and msg.toolCallId:
                presentToolResultIds.add(msg.toolCallId)

        survivingCallIds: set[str] = set()
        for cm in contextMessages:
            msg = cm.chatMessage
            if msg.role == ERole.ASSISTANT and msg.toolCalls:
                for tc in msg.toolCalls:
                    if tc.id in presentToolResultIds:
                        survivingCallIds.add(tc.id)

        sanitized: list[ChatMessage] = []
        for cm in contextMessages:
            msg = cm.chatMessage
            if msg.role == ERole.ASSISTANT and msg.toolCalls:
                keptCalls = [tc for tc in msg.toolCalls if tc.id in survivingCallIds]
                if not keptCalls:
                    sanitized.append(ChatMessage(role=msg.role, content=msg.content, cacheControl=msg.cacheControl))
                elif len(keptCalls) == len(msg.toolCalls):
                    sanitized.append(msg)
                else:
                    sanitized.append(
                        ChatMessage(role=msg.role, content=msg.content, toolCalls=keptCalls, cacheControl=msg.cacheControl)
                    )
            elif msg.role == ERole.TOOL:
                if msg.toolCallId in survivingCallIds:
                    sanitized.append(msg)
            else:
                sanitized.append(msg)

        return sanitized

    @staticmethod
    def _IsRetryable(error: LLMError) -> bool:
        """判断 LLMError 是否可重试。

        可重试：429 (Rate Limit)、5xx (Server Error)、网络无状态码。
        不可重试：400、401、403、404 等客户端错误。
        """
        if error.statusCode is None:
            return True
        return error.statusCode in (429, 500, 502, 503, 504)

    # ---- 魔法方法 ----

    def __repr__(self) -> str:
        modelName = self._llmComponent.ModelName if self._llmComponent.llm else "<no model>"
        return (
            f"Agent(state={self._dataComp.state.name}, "
            f"model={modelName}, "
            f"session={self._session.sessionId[:8]}...)"
        )
