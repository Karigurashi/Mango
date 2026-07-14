"""CommandComponent —— 指令系统组件，由 BaseChannel 直接持有。

维护 CommandRegistry，负责指令注册与异步分发。
指令响应通过 channel.OnSendResponseAsync 投递到平台层。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from common.cancellationToken import CancellationToken

from ...channelComponent import IChannelComponent
from ...channelMessage import ChannelMessage
from ...eChannelState import EChannelState
from ..group import GroupContext
from .builtinCommands import RegisterBuiltinCommands
from .command import Command
from .commandContext import CommandContext
from .commandRegistry import CommandRegistry

if TYPE_CHECKING:
    from ...baseChannel import BaseChannel


class CommandComponent(IChannelComponent):
    """指令系统组件 —— 指令注册表与异步分发。

    由 BaseChannel.__init__ 创建并初始化，通过 channel._commandComponent 访问。
    OnDestroy 时无需特殊清理。

    用法::

        channel = BaseChannel()
        channel._commandComponent.RegisterCommand(Command("hello", "Say hello", _HelloAsync))
        await channel._commandComponent.DispatchAsync(group, message)
    """

    def __init__(self) -> None:
        self._channel: Optional[BaseChannel] = None
        self._commandRegistry: CommandRegistry = CommandRegistry()

    # ---- IComponent 生命周期 ----

    def OnInitialize(self, channel: BaseChannel) -> None:
        """挂载后创建 CommandRegistry 并注册内置指令。"""
        self._channel = channel
        self._commandRegistry = CommandRegistry(channel._config.commandPrefix)
        RegisterBuiltinCommands(self._commandRegistry)

    def OnDestroy(self) -> None:
        """卸载时无特殊清理。"""
        pass

    # ---- 属性 ----

    @property
    def CommandRegistry(self) -> CommandRegistry:
        """指令注册表实例。"""
        return self._commandRegistry

    # ---- 注册 ----

    def RegisterCommand(self, command: Command) -> None:
        """注册一条指令到注册表。

        Args:
            command: Command 实例。
        """
        self._commandRegistry.Register(command)

    # ---- 分发 ----

    async def DispatchAsync(
        self,
        groupContext: GroupContext,
        message: ChannelMessage,
        cancellationToken: Optional[CancellationToken] = None,
    ) -> None:
        """分发指令并投递响应。

        指令若请求退出（WantsExit），直接将 Channel 状态置为 STOPPING，
        由外部主循环检测并停止。

        Args:
            groupContext: 当前群组上下文。
            message: 含前缀的原始消息。
            cancellationToken: 取消令牌。
        """
        channel = self._channel  # type: ignore[assignment]
        ctx = channel.CreateCommandContext(groupContext, message)
        await self._commandRegistry.DispatchAsync(message.content, ctx)

        if ctx.HasResponse:
            await channel.OnSendResponseAsync(
                groupContext.groupId,
                ctx.GetResponseText(),
                cancellationToken,
            )

        if ctx.WantsExit:
            channel._state = EChannelState.STOPPING
