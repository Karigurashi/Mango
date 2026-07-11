"""GroupContext —— 单群上下文，持有一个 Agent 实例并管理消息串行处理。

每个群（如飞书群、Discord Channel）对应一个 GroupContext，
内含独立的 Agent + Session，群间完全隔离。Agent 内部 _runLock
已保证同一 Agent 不并发重入，GroupContext 不再额外加锁。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from agent import Agent, AgentStreamEvent, EventBusComponent
from common.cancellationToken import CancellationToken
from common.logger import Logger

from .channelMessage import ChannelMessage

if TYPE_CHECKING:
    from .baseChannel import BaseChannel


class GroupContext:
    """单群上下文 —— 一个 Agent 实例 + 消息串行处理。

    不自行加锁：Agent 内部的 _runLock 已保证串行。取消令牌由调用方
    自行管理，GroupContext 仅透传给 Agent。

    Attributes:
        groupId: 群唯一标识。
        groupName: 群显示名称。
        agent: 该群专属的 Agent 实例。
    """

    def __init__(
        self,
        channel: BaseChannel,
        groupId: str,
        groupName: str,
        agent: Agent,
    ) -> None:
        self._channel: BaseChannel = channel
        self.groupId: str = groupId
        self.groupName: str = groupName
        self.agent: Agent = agent

        self._token: Optional[CancellationToken] = None
        self._eventBus: EventBusComponent = agent.GetComponent(EventBusComponent)
        self._eventBus.AddListener(self._OnAgentEvent)

    # ---- 消息处理 ----

    async def SendMessageAsync(
        self,
        message: ChannelMessage,
        cancellationToken: Optional[CancellationToken] = None,
    ) -> None:
        """处理一条入站消息。

        Agent 内部 _runLock 保证串行，调用方无需额外加锁。

        Args:
            message: 标准化入站消息。
            cancellationToken: 取消令牌，透传给 Agent。
        """
        self._token = cancellationToken or CancellationToken()
        try:
            await self.agent.RunStreamAsync(message.content, self._token)
        except Exception as exc:
            Logger.Error(f"GroupContext[{self.groupId}] agent run failed: {exc}")
        finally:
            self._token = None

    # ---- 事件监听 ----

    def _OnAgentEvent(self, event: AgentStreamEvent) -> None:
        """同步事件监听器 —— 将 Agent 事件转发给 BaseChannel。"""
        self._channel.OnAgentEventSync(self.groupId, event)

    # ---- 生命周期 ----

    def Cancel(self) -> None:
        """取消当前正在执行的 Agent 运行。"""
        if self._token is not None:
            self._token.Cancel()
            self._token = None

    def Destroy(self) -> None:
        """销毁 Agent 实例，移除事件监听。"""
        self.Cancel()
        self._eventBus.RemoveListener(self._OnAgentEvent)
        self.agent.Destroy()

    def __repr__(self) -> str:
        return f"GroupContext(groupId={self.groupId}, groupName={self.groupName})"
