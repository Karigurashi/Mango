"""LoggingComponent —— Agent 级结构化日志组件，记录运行时可观测事件。

将 LLM 调用、工具执行、上下文压缩、状态迁移等关键事件以结构化格式记录，
支持 TEXT（人类可读）和 JSONL（机器解析）两种输出格式。

与 common.logger 的关系：
- common.Logger 是开发调试日志（print 级，全局静态）
- LoggingComponent 是运行运营日志（事件级，Agent 实例隔离，可序列化）

两者互补，不替代。

作为 IComponent 可挂载到 BaseAgent，通过 OnInitialize 感知 Agent 上下文。
"""

from __future__ import annotations

import os
import time
from typing import Any, TYPE_CHECKING

from agent.core.baseComponent import IComponent
from common.logger import Logger

from .eLogEventType import ELogEventType
from .logEvent import LogEvent

if TYPE_CHECKING:
    from agent.core.baseAgent import BaseAgent


class LoggingComponent(IComponent):
    """Agent 级结构化日志组件 —— 记录运行时可观测事件并持久化。

    提供 6 类事件的记录方法：
    - LogLLMCall: LLM 调用完成（含 token 用量、耗时、重试次数）
    - LogToolExecution: 工具执行完成（含工具名、耗时、成功/失败）
    - LogCompaction: 上下文压缩完成（含压缩前/后 token、紧急度）
    - LogStateChange: Agent 状态迁移
    - LogRunStart / LogRunEnd: Run 生命周期起止

    事件累积在内存中，按配置刷新到文件：
    - logFlushPerTurn=True 时，每轮 AfterTurn 自动刷新
    - OnDestroy 时强制刷新确保无丢失

    用法::

        agent = Agent(llm)
        loggingComp = agent.GetComponent(LoggingComponent)
        metrics = loggingComp.GetSessionMetrics()
    """

    def __init__(self) -> None:
        self._events: list[LogEvent] = []
        self._sessionId: str = ""
        self._logDir: str = ".contex/log"
        self._logFormat: str = "TEXT"  # TEXT / JSON
        self._logFlushPerTurn: bool = True
        self._flushed: bool = False

    # ---- IComponent 生命周期 ----

    def OnInitialize(self, agent: BaseAgent) -> None:
        """挂载后初始化，从 DataComponent 获取日志配置，从 SessionComponent 获取会话 ID。"""
        from agent.component.data.dataComponent import DataComponent
        from agent.component.session.sessionComponent import SessionComponent

        dataComp = agent.GetComponent(DataComponent)
        if dataComp is not None:
            config = dataComp.config
            self._logDir = config.logDir
            self._logFormat = config.logFormat
            self._logFlushPerTurn = config.logFlushPerTurn

        session = agent.GetComponent(SessionComponent)
        if session is not None:
            self._sessionId = session.sessionId[:8]

    def OnDestroy(self) -> None:
        """从 BaseAgent 卸载时回调，强制刷新未写出的事件。"""
        if self._events:
            self.Flush()

    # ---- 事件记录方法 ----

    def LogLLMCall(
        self,
        turnIndex: int,
        modelName: str,
        inputTokens: int,
        outputTokens: int,
        duration: float,
        streaming: bool,
        retryCount: int = 0,
        success: bool = True,
    ) -> None:
        """记录 LLM 调用事件。

        Args:
            turnIndex: 推理轮次。
            modelName: 模型名称。
            inputTokens: 输入 token 数。
            outputTokens: 输出 token 数。
            duration: 调用耗时秒数。
            streaming: 是否流式调用。
            retryCount: 本次重试次数。
            success: 是否成功。
        """
        self._events.append(LogEvent(
            eventType=ELogEventType.LLM_CALL,
            sessionId=self._sessionId,
            turnIndex=turnIndex,
            duration=duration,
            metadata={
                "model": modelName,
                "inputTokens": inputTokens,
                "outputTokens": outputTokens,
                "totalTokens": inputTokens + outputTokens,
                "streaming": streaming,
                "retryCount": retryCount,
                "success": success,
            },
        ))

    def LogToolExecution(
        self,
        turnIndex: int,
        toolName: str,
        duration: float,
        success: bool,
        resultChars: int = 0,
    ) -> None:
        """记录工具执行事件。

        Args:
            turnIndex: 推理轮次。
            toolName: 工具名称。
            duration: 执行耗时秒数。
            success: 是否成功。
            resultChars: 结果字符数。
        """
        self._events.append(LogEvent(
            eventType=ELogEventType.TOOL_EXECUTION,
            sessionId=self._sessionId,
            turnIndex=turnIndex,
            duration=duration,
            metadata={
                "tool": toolName,
                "success": success,
                "resultChars": resultChars,
            },
        ))

    def LogCompaction(
        self,
        turnIndex: int,
        urgency: str,
        tokensBefore: int,
        tokensAfter: int,
        messagesCompacted: int,
        duration: float,
        llmUsed: bool,
    ) -> None:
        """记录上下文压缩事件。

        Args:
            turnIndex: 推理轮次。
            urgency: 压缩紧急度（NONE/MILD/MODERATE/SEVERE）。
            tokensBefore: 压缩前 token 数。
            tokensAfter: 压缩后 token 数。
            messagesCompacted: 被压缩消息数。
            duration: 压缩耗时秒数。
            llmUsed: 是否调用了 LLM 摘要。
        """
        self._events.append(LogEvent(
            eventType=ELogEventType.COMPACTION,
            sessionId=self._sessionId,
            turnIndex=turnIndex,
            duration=duration,
            metadata={
                "urgency": urgency,
                "tokensBefore": tokensBefore,
                "tokensAfter": tokensAfter,
                "tokensFreed": tokensBefore - tokensAfter,
                "messagesCompacted": messagesCompacted,
                "llmUsed": llmUsed,
            },
        ))

    def LogStateChange(
        self,
        turnIndex: int,
        fromState: str,
        toState: str,
    ) -> None:
        """记录 Agent 状态迁移事件。

        Args:
            turnIndex: 推理轮次。
            fromState: 迁移前状态。
            toState: 迁移后状态。
        """
        self._events.append(LogEvent(
            eventType=ELogEventType.STATE_CHANGE,
            sessionId=self._sessionId,
            turnIndex=turnIndex,
            metadata={
                "from": fromState,
                "to": toState,
            },
        ))

    def LogRunStart(self, userMessage: str) -> None:
        """记录 Run 启动事件。

        Args:
            userMessage: 用户输入消息（截断到 100 字符）。
        """
        self._events.append(LogEvent(
            eventType=ELogEventType.RUN_START,
            sessionId=self._sessionId,
            metadata={
                "userMessage": userMessage[:100],
            },
        ))

    def LogRunEnd(
        self,
        totalTurns: int,
        totalDuration: float,
        totalTokens: int,
        endState: str,
    ) -> None:
        """记录 Run 结束事件。

        Args:
            totalTurns: 总推理轮次。
            totalDuration: 总耗时秒数。
            totalTokens: 总 token 消耗。
            endState: 结束状态（FINISHED/ERROR/CANCELLED）。
        """
        self._events.append(LogEvent(
            eventType=ELogEventType.RUN_END,
            sessionId=self._sessionId,
            duration=totalDuration,
            metadata={
                "totalTurns": totalTurns,
                "totalTokens": totalTokens,
                "endState": endState,
            },
        ))

    def LogContextLifecycle(
        self,
        turnIndex: int,
        phase: str,
        tokenCount: int = 0,
        messageCount: int = 0,
    ) -> None:
        """记录上下文生命周期事件。

        Args:
            turnIndex: 推理轮次。
            phase: 阶段名（Ingest/Assemble/Compact/AfterTurn）。
            tokenCount: 当前 token 数。
            messageCount: 当前消息数。
        """
        self._events.append(LogEvent(
            eventType=ELogEventType.CONTEXT_LIFECYCLE,
            sessionId=self._sessionId,
            turnIndex=turnIndex,
            metadata={
                "phase": phase,
                "tokens": tokenCount,
                "messages": messageCount,
            },
        ))

    # ---- 自定义事件 ----

    def LogCustom(
        self,
        turnIndex: int,
        name: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """记录自定义事件（供外部扩展使用）。

        Args:
            turnIndex: 推理轮次。
            name: 事件名称。
            metadata: 事件元数据。
        """
        meta = metadata or {}
        meta["name"] = name
        self._events.append(LogEvent(
            eventType=ELogEventType.CONTEXT_LIFECYCLE,
            sessionId=self._sessionId,
            turnIndex=turnIndex,
            metadata=meta,
        ))

    # ---- AfterTurn 刷新 ----

    def OnAfterTurnAsync(self) -> None:
        """AfterTurn 时调用，按配置决定是否刷新到文件。"""
        if self._logFlushPerTurn and self._events:
            self.Flush()

    # ---- 输出 ----

    def Flush(self) -> None:
        """将累积的事件写入日志文件，写后清空内存缓冲。"""
        if not self._events:
            return

        try:
            os.makedirs(self._logDir, exist_ok=True)

            ext = ".jsonl" if self._logFormat == "JSON" else ".log"
            filename = f"{self._sessionId}_{int(time.time())}{ext}"
            filepath = os.path.join(self._logDir, filename)

            with open(filepath, "a", encoding="utf-8") as f:
                for event in self._events:
                    if self._logFormat == "JSON":
                        f.write(event.ToJsonLine() + "\n")
                    else:
                        f.write(event.ToTextLine() + "\n")

            self._events.clear()
        except OSError as exc:
            Logger.Warning(f"LoggingComponent: flush failed: {exc}")

    # ---- 聚合指标 ----

    def GetTurnMetrics(self, turnIndex: int) -> dict[str, Any]:
        """获取指定轮次的聚合指标。

        Returns:
            含 llmCalls/toolCalls/totalTokens/totalDuration 的字典。
        """
        turnEvents = [e for e in self._events if e.turnIndex == turnIndex]

        llmCalls = [e for e in turnEvents if e.eventType == ELogEventType.LLM_CALL]
        toolCalls = [e for e in turnEvents if e.eventType == ELogEventType.TOOL_EXECUTION]
        compactions = [e for e in turnEvents if e.eventType == ELogEventType.COMPACTION]

        totalInputTokens = sum(e.metadata.get("inputTokens", 0) for e in llmCalls)
        totalOutputTokens = sum(e.metadata.get("outputTokens", 0) for e in llmCalls)
        llmDuration = sum(e.duration for e in llmCalls if e.duration >= 0)
        toolDuration = sum(e.duration for e in toolCalls if e.duration >= 0)

        return {
            "turnIndex": turnIndex,
            "llmCalls": len(llmCalls),
            "inputTokens": totalInputTokens,
            "outputTokens": totalOutputTokens,
            "totalTokens": totalInputTokens + totalOutputTokens,
            "llmDuration": round(llmDuration, 3),
            "toolCalls": len(toolCalls),
            "toolDuration": round(toolDuration, 3),
            "compactions": len(compactions),
        }

    def GetSessionMetrics(self) -> dict[str, Any]:
        """获取整个会话的聚合指标。

        Returns:
            含 totalTurns/totalLLMCalls/totalToolCalls/totalTokens/totalDuration 的字典。
        """
        llmCalls = [e for e in self._events if e.eventType == ELogEventType.LLM_CALL]
        toolCalls = [e for e in self._events if e.eventType == ELogEventType.TOOL_EXECUTION]
        compactions = [e for e in self._events if e.eventType == ELogEventType.COMPACTION]

        maxTurn = max((e.turnIndex for e in self._events if e.turnIndex >= 0), default=-1)
        totalInputTokens = sum(e.metadata.get("inputTokens", 0) for e in llmCalls)
        totalOutputTokens = sum(e.metadata.get("outputTokens", 0) for e in llmCalls)

        return {
            "sessionId": self._sessionId,
            "totalTurns": maxTurn + 1 if maxTurn >= 0 else 0,
            "totalLLMCalls": len(llmCalls),
            "totalToolCalls": len(toolCalls),
            "totalCompactions": len(compactions),
            "inputTokens": totalInputTokens,
            "outputTokens": totalOutputTokens,
            "totalTokens": totalInputTokens + totalOutputTokens,
            "totalEvents": len(self._events),
        }

    # ---- 属性 ----

    @property
    def EventCount(self) -> int:
        """当前内存中的事件数。"""
        return len(self._events)

    @property
    def LogDir(self) -> str:
        return self._logDir

    def __repr__(self) -> str:
        return f"LoggingComponent(session={self._sessionId}, events={len(self._events)})"