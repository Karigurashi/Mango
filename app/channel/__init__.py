"""BaseChannel 框架 —— 多群消息路由基类，统一 1 App → N 群 → 1 Agent/群 模式。

各平台适配器（飞书、Discord、VSCode Chat 等）继承 BaseChannel 并实现
平台 I/O 钩子即可接入 Agent 体系。

Usage::

    class FeishuChannel(BaseChannel):
        async def OnSendResponseAsync(self, groupId, content, cancellationToken=None):
            await self._api.SendMessage(groupId, content)

        async def OnStartAsync(self, cancellationToken=None):
            await self._api.StartWebhook()

    channel = FeishuChannel(ChannelConfig(modelName="deepseek-chat"))
    await channel.StartAsync()

    # Webhook 收到消息时
    msg = ChannelMessage(groupId="group_123", userId="user_456", content="你好")
    await channel.ReceiveMessageAsync(msg)
"""

from .baseChannel import BaseChannel
from .channelComponent import IChannelComponent
from .channelConfig import ChannelConfig
from .channelMessage import ChannelMessage
from .component.command import (
    Command,
    CommandComponent,
    CommandContext,
    CommandRegistry,
    RegisterBuiltinCommands,
)
from .component.group import GroupComponent, GroupContext
from .eChannelState import EChannelState

__all__ = [
    "BaseChannel",
    "ChannelConfig",
    "ChannelMessage",
    "Command",
    "CommandComponent",
    "CommandContext",
    "CommandRegistry",
    "EChannelState",
    "GroupComponent",
    "GroupContext",
    "IChannelComponent",
    "RegisterBuiltinCommands",
]
