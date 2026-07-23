"""GroupContext —— 单群上下文，持有一个 Agent 实例并管理消息串行处理。

每个群（如飞书群、Discord Channel）对应一个 GroupContext，
内含独立的 Agent + Session，群间完全隔离。

线程模型::

    主事件循环                     Group 线程（每群一个）
    ┌──────────────────┐          ┌──────────────────────┐
    │ ReceiveMessageAsync│         │ while _running:       │
    │  → PostMessage     │──queue──→│   item = queue.get() │
    │  → 立即返回        │         │   → run_until_complete│
    │  （主循环不被阻塞） │         │     agent.RunStreamAsync│
    └──────────────────┘          │   → 事件经 EventBus   │
                                  │     → OnAgentEventSync│
                                  └──────────────────────┘

PostMessage（非阻塞）: 供多群 Channel（如飞书）使用，
    消息入队后立即返回，Agent 在群线程中串行执行。
SendMessageAsync（阻塞）: 供单群交互式 Channel（如 CLI）使用，
    在调用方事件循环中直接 await Agent，用户等待响应。

Agent 实例完全封装在 GroupContext 内部，不对外暴露。
外部通过查询方法获取模型名、会话 ID 等信息，无需感知 Agent 类型。
"""

from __future__ import annotations

import asyncio
import queue
import threading
from typing import TYPE_CHECKING, Optional

from common.cancellationToken import CancellationToken
from common.logger import Logger

from ...channelMessage import ChannelMessage

if TYPE_CHECKING:
    from agent import Agent, AgentStreamEvent, EventBusComponent, LLMComponent, SessionComponent
    from ...baseChannel import BaseChannel


class GroupContext:
    """单群上下文 —— 一个 Agent 实例 + 消息串行处理。

    每个群拥有独立的守护线程和事件循环，Agent 在群线程中串行执行。
    Agent 内部运行锁（LoopComponent.runLock）保证同一 Agent 不并发重入（在同一事件循环中生效）。

    两种消息分发方式:
        - PostMessage: 非阻塞，消息入队后立即返回。群线程串行消费。
          适用于多群 Channel（飞书），主事件循环不被 Agent 阻塞。
        - SendMessageAsync: 阻塞，在调用方事件循环中直接 await Agent。
          适用于单群交互式 Channel（CLI），用户需要等待响应。

    注意: 同一 GroupContext 不应混用两种方式。CLI 用 SendMessageAsync，
    飞书用 PostMessage。混用会导致 Agent 运行锁跨事件循环失效。

    Attributes:
        groupId: 群唯一标识。
        groupName: 群显示名称。
    """

    def __init__(
        self,
        channel: BaseChannel,
        groupId: str,
        groupName: str,
        agent: Agent,
    ) -> None:
        from agent.component.eventBus.eventBusComponent import EventBusComponent
        self._channel: BaseChannel = channel
        self._agent: Agent = agent
        self.groupId: str = groupId
        self.groupName: str = groupName

        self._token: Optional[CancellationToken] = None
        self._eventBus: EventBusComponent = agent.GetComponent(EventBusComponent)
        self._eventBus.AddListener(self._OnAgentEvent)

        # ---- 群线程管理 ----
        self._messageQueue: queue.Queue = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._running: bool = False

    # ---- 群线程生命周期 ----

    def Start(self) -> None:
        """启动群 Agent 线程。

        创建守护线程，在独立事件循环中串行消费消息队列。
        线程在 Destroy 时自动退出。
        """
        if self._thread is not None:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._RunAgentLoop,
            name=f"group-{self.groupId}",
            daemon=True,
        )
        self._thread.start()
        Logger.Debug(f"GroupContext[{self.groupId}] agent thread started")

    # ---- 非阻塞分发（多群 Channel 使用） ----

    def PostMessage(
        self,
        message: ChannelMessage,
        cancellationToken: Optional[CancellationToken] = None,
    ) -> None:
        """将消息入队到群线程（非阻塞，纳秒级）。

        消息在群线程中串行处理，调用方立即返回。
        适用于多群 Channel（飞书），主事件循环不被 Agent 阻塞。

        Args:
            message: 标准化入站消息。
            cancellationToken: 取消令牌，透传给 Agent。
        """
        self._messageQueue.put_nowait((message, cancellationToken))

    # ---- 阻塞分发（单群交互式 Channel 使用） ----

    async def SendMessageAsync(
        self,
        message: ChannelMessage,
        cancellationToken: Optional[CancellationToken] = None,
    ) -> None:
        """在调用方事件循环中直接运行 Agent（阻塞）。

        适用于单群交互式 Channel（CLI），用户需要等待 Agent 响应。
        不经过群线程，直接在当前事件循环中 await Agent。

        注意: 不要与 PostMessage 混用，否则 Agent 运行锁
        会跨事件循环失效。

        Args:
            message: 标准化入站消息。
            cancellationToken: 取消令牌，透传给 Agent。
        """
        self._token = cancellationToken or CancellationToken()
        try:
            await self._agent.RunStreamAsync(message.content, self._token)
        except Exception as exc:
            Logger.Error(f"GroupContext[{self.groupId}] agent run failed: {exc}")
        finally:
            self._token = None

    # ---- 群线程主循环 ----

    def _RunAgentLoop(self) -> None:
        """群 Agent 线程入口：创建独立事件循环，串行消费消息队列。

        每条消息通过 run_until_complete 在本线程的事件循环中执行，
        Agent 内部运行锁在同一循环中生效，保证串行。
        收到 None 哨兵或 _running=False 时退出。
        """
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            while self._running:
                item = self._messageQueue.get()
                if item is None:
                    break
                message, cancellationToken = item
                try:
                    self._loop.run_until_complete(
                        self._RunAgentAsync(message, cancellationToken)
                    )
                except Exception as exc:
                    Logger.Error(f"GroupContext[{self.groupId}] agent thread error: {exc}")
        finally:
            self._loop.close()
            Logger.Debug(f"GroupContext[{self.groupId}] agent thread exited")

    async def _RunAgentAsync(
        self,
        message: ChannelMessage,
        cancellationToken: Optional[CancellationToken],
    ) -> None:
        """在群线程事件循环中执行单条消息的 Agent 推理。

        Args:
            message: 入站消息。
            cancellationToken: 取消令牌。
        """
        self._token = cancellationToken or CancellationToken()
        try:
            await self._agent.RunStreamAsync(message.content, self._token)
        except Exception as exc:
            Logger.Error(f"GroupContext[{self.groupId}] agent run failed: {exc}")
        finally:
            self._token = None

    # ---- 事件监听 ----

    def _OnAgentEvent(self, event: AgentStreamEvent) -> None:
        """同步事件监听器 —— 将 Agent 事件转发给 BaseChannel。

        在群线程中被 EventBus 同步调用（PostMessage 模式），
        或在主事件循环中被调用（SendMessageAsync 模式）。
        """
        self._channel.OnAgentEventSync(self.groupId, event)

    # ---- 查询 API（内部访问 _agent，不暴露 Agent 类型） ----

    def GetModelName(self) -> str:
        """获取当前群组 Agent 使用的模型名称。"""
        from agent.component.llm.llmComponent import LLMComponent
        return self._agent.GetComponent(LLMComponent).modelName

    def GetActiveSessionId(self) -> int:
        """获取当前活跃会话 ID。"""
        from agent.component.session.sessionComponent import SessionComponent
        return self._agent.GetComponent(SessionComponent).ActiveSessionId

    def GetLastTokenUsage(self) -> tuple[int, int, float]:
        """获取最近一次推理的 Token 用量。

        Returns:
            (promptTokens, completionTokens, cacheHitRate)
        """
        from agent.component.llm.llmComponent import LLMComponent
        llm = self._agent.GetComponent(LLMComponent)
        return llm.LastPromptTokens, llm.LastCompletionTokens, llm.LastCacheHitRate

    # ---- 生命周期 ----

    def Cancel(self) -> None:
        """取消当前正在执行的 Agent 运行（线程安全）。

        仅读取 _token 并调用 Cancel()，不修改 _token，
        避免与群线程的 finally 块产生竞态。
        """
        token = self._token
        if token is not None:
            token.Cancel()

    def Destroy(self) -> None:
        """停止群线程，取消 Agent 运行，销毁 Agent 实例。

        1. 设置 _running=False，向队列投入 None 哨兵唤醒线程。
        2. 取消正在执行的 Agent 运行。
        3. 等待群线程退出（最多 5 秒）。
        4. 移除事件监听器，销毁 Agent。
        """
        self._running = False
        self.Cancel()
        self._messageQueue.put(None)
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        self._eventBus.RemoveListener(self._OnAgentEvent)
        self._agent.Destroy()

    def __repr__(self) -> str:
        return f"GroupContext(groupId={self.groupId}, groupName={self.groupName})"
