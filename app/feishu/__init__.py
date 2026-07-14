"""飞书机器人通道模块 —— 基于 BaseChannel 框架的飞书平台适配器。

通过 lark-oapi SDK 的 WebSocket 长连接接收飞书群消息，
每个群聊 (chat_id) 创建独立 Agent 实例，群间完全隔离。
Agent 响应以文本消息形式投递到对应群聊。

Usage::

    from app.feishu import FeishuChannel, FeishuConfig

    channel = FeishuChannel(FeishuConfig(
        appId="cli_xxx",
        appSecret="xxx",
        modelName="deepseek-mid",
    ))
    channel.Start()  # 阻塞直到 Ctrl+C
"""

from ..channel import BaseChannel, ChannelConfig, ChannelMessage, EChannelState
from .feishuApi import FeishuApi
from .feishuCardComponent import FeishuCardComponent
from .feishuChannel import FeishuChannel
from .feishuConfig import FeishuConfig

__all__ = [
    "FeishuChannel",
    "FeishuConfig",
    "FeishuApi",
    "FeishuCardComponent",
    "BaseChannel",
    "ChannelConfig",
    "ChannelMessage",
    "EChannelState",
]
