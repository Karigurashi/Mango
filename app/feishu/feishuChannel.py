"""FeishuChannel —— 飞书机器人通道适配器，继承 BaseChannel。

通过 lark-oapi SDK 的 WebSocket 长连接接收飞书消息事件，
将消息路由到 BaseChannel 的群组消息处理流程。每个飞书群聊
(chat_id) 对应一个独立的 Agent 实例，群间完全隔离。

三线程架构（对标 Dify 等商业方案，Agent 推理与 I/O 路由分离）::

    主事件循环（轻量）        WebSocket 线程          卡片消费线程
    ┌──────────────────┐     ┌──────────────┐      ┌──────────────┐
    │ 消息路由          │←coro│ ws.Client     │      │ queue.get()  │
    │ ReceiveMessageAsync│     │ _OnMessageRev │      │ 构建卡片 JSON │
    │  → PostMessage    │     └──────────────┘      │ HTTP PATCH   │
    │  （纳秒级，不阻塞）│                           └──────────────┘
    └──────────────────┘
         │ queue
         ↓
    Group 线程池（每群一个，独立事件循环）
    ┌──────────────────┐ ┌──────────────────┐
    │ Group A 线程       │ │ Group B 线程       │
    │ agent.RunStreamAsync│ │ agent.RunStreamAsync│
    │  → EventBus 事件   │ │  → EventBus 事件   │
    │  → OnAgentEventSync│ │  → OnAgentEventSync│
    │  → queue.put_nowait│ │  → queue.put_nowait│
    └──────────────────┘ └──────────────────┘

Usage::

    from app.feishu import FeishuChannel, FeishuConfig

    channel = FeishuChannel(FeishuConfig(
        appId="cli_xxx",
        appSecret="xxx",
        modelName="deepseek-mid",
    ))
    channel.Start()  # 阻塞直到退出
"""

from __future__ import annotations

import asyncio
import json
import signal
import threading
from typing import Optional, TYPE_CHECKING, Coroutine

import lark_oapi as lark

from agent import AgentStreamEvent
from common.cancellationToken import CancellationToken
from common.logger import Logger

from ..channel import BaseChannel, ChannelConfig, ChannelMessage, EChannelState
from .feishuApi import FeishuApi
from .feishuCardComponent import FeishuCardComponent
from .feishuConfig import FeishuConfig

if TYPE_CHECKING:
    pass


class FeishuChannel(BaseChannel):
    """飞书机器人通道适配器 —— BaseChannel 的飞书平台实现。

    通过 WebSocket 长连接接收飞书群消息，每个群聊 (chat_id) 创建
    独立 Agent 实例。Agent 响应通过 FeishuCardComponent 在独立线程
    实时更新流式卡片（Markdown 格式），不阻塞 Agent 推理。

    线程模型:
        - 主事件循环: 消息路由（ReceiveMessageAsync → PostMessage），
          纳秒级非阻塞，不被 Agent 推理阻塞。
        - WebSocket 线程: lark.ws.Client.start()（阻塞，守护线程）。
        - Group 线程池: 每群一个守护线程，独立事件循环串行执行 Agent。
          群间真正并行，互不阻塞。
        - 卡片消费线程: FeishuCardComponent 独立消费 Agent 事件，
          通过 HTTP API 发送/更新卡片。

    Attributes:
        _feishuConfig: 飞书配置。
        _api: 飞书 API 客户端。
        _loop: 主事件循环引用（供 WebSocket 线程跨线程调度）。
        _wsClient: lark-oapi WebSocket 客户端。
        _wsThread: WebSocket 守护线程。
        _cardComponent: 流式卡片组件（独立线程消费事件）。
    """

    def __init__(
        self,
        config: Optional[FeishuConfig] = None,
    ) -> None:
        feishuConfig = config or FeishuConfig()
        channelConfig = ChannelConfig(
            modelName=feishuConfig.modelName,
            commandPrefix=feishuConfig.commandPrefix,
        )
        super().__init__(channelConfig)

        self._feishuConfig: FeishuConfig = feishuConfig
        self._api: FeishuApi = FeishuApi(feishuConfig.appId, feishuConfig.appSecret)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._wsClient: Optional[lark.ws.Client] = None
        self._wsThread: Optional[threading.Thread] = None

        # 流式卡片组件（独立线程消费 Agent 事件）
        self._cardComponent: FeishuCardComponent = FeishuCardComponent()
        self._cardComponent.OnInitialize(self)

    # ---- BaseChannel 钩子 ----

    async def OnStartAsync(
        self,
        cancellationToken: Optional[CancellationToken] = None,
    ) -> None:
        """override: 启动飞书 WebSocket 长连接，阻塞直到收到停止信号。

        在守护线程中运行 lark.ws.Client.start()（阻塞调用），
        主协程以 0.5s 间隔轮询 _state，STOPPING 时退出循环。
        退出后调用 StopAsync 完成清理。

        Args:
            cancellationToken: 取消令牌。
        """
        self._loop = asyncio.get_running_loop()

        # 注册 SIGINT 处理器（仅在主线程中可用）
        try:
            signal.signal(signal.SIGINT, self._OnInterrupt)
        except (ValueError, OSError):
            Logger.Warning("FeishuChannel: cannot register SIGINT handler (not in main thread)")

        # 构建事件处理器
        eventHandler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(self._OnMessageReceive)
            .build()
        )

        # 创建 WebSocket 客户端并在守护线程中启动
        self._wsClient = lark.ws.Client(
            self._feishuConfig.appId,
            self._feishuConfig.appSecret,
            event_handler=eventHandler,
            auto_reconnect=True,
        )
        self._wsThread = threading.Thread(
            target=self._wsClient.start,
            name="feishu-ws",
            daemon=True,
        )
        self._wsThread.start()
        Logger.Info("FeishuChannel: WebSocket client started")

        # 主循环：等待停止信号
        try:
            while self._state == EChannelState.RUNNING:
                await asyncio.sleep(0.5)
        finally:
            await self.StopAsync()

    async def OnStopAsync(
        self,
        cancellationToken: Optional[CancellationToken] = None,
    ) -> None:
        """override: 断开 WebSocket 连接，销毁卡片组件。"""
        if self._wsClient is not None:
            try:
                self._wsClient._disconnect()
            except Exception as exc:
                Logger.Warning(f"FeishuChannel: WebSocket disconnect error: {exc}")
            self._wsClient = None

        # 销毁卡片组件（停止消费线程，等待剩余 HTTP 完成）
        self._cardComponent.OnDestroy()

    def OnAgentEventSync(
        self,
        groupId: str,
        event: AgentStreamEvent,
    ) -> None:
        """override: 将 Agent 事件入队到卡片组件（纳秒级，不阻塞推理）。

        Args:
            groupId: 事件来源群组 ID (chat_id)。
            event: Agent 流式事件。
        """
        self._cardComponent.HandleEvent(groupId, event)

    async def OnSendResponseAsync(
        self,
        groupId: str,
        content: str,
        cancellationToken: Optional[CancellationToken] = None,
    ) -> None:
        """override: 将指令响应发送到飞书群聊。

        Args:
            groupId: 目标群聊 ID (chat_id)。
            content: 响应文本。
            cancellationToken: 取消令牌。
        """
        await self._api.SendTextAsync(groupId, content, cancellationToken)

    # ---- WebSocket 事件处理 ----

    def _OnMessageReceive(self, data: object) -> None:
        """飞书消息接收事件回调（在 WebSocket 线程中执行）。

        将飞书原始事件转换为 ChannelMessage，通过
        run_coroutine_threadsafe 调度到主事件循环。

        Args:
            data: lark-oapi P2ImMessageReceiveV1 事件对象。
        """
        try:
            msg = data.event.message
            sender = data.event.sender

            # 仅处理文本消息
            if msg.message_type != "text":
                return

            content = self._ExtractText(msg.content, msg.mentions)
            if not content:
                return

            channelMsg = ChannelMessage(
                groupId=msg.chat_id,
                userId=sender.sender_id.open_id,
                content=content,
                userName=sender.sender_id.open_id,
            )

            # 跨线程调度到主事件循环
            if self._loop is not None and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    self.ReceiveMessageAsync(channelMsg),
                    self._loop,
                )
        except Exception as exc:
            Logger.Error(f"FeishuChannel._OnMessageReceive failed: {exc}")

    # ---- 文本提取 ----

    @staticmethod
    def _ExtractText(contentJson: str, mentions: Optional[list]) -> str:
        """从飞书消息内容 JSON 中提取纯文本，去除 @提及占位符。

        飞书文本消息 content 格式::

            {"text": "hello world"}

        群聊 @机器人 时::

            {"text": "@_user_1 hello"}
            mentions: [{"key": "@_user_1", "id": {"open_id": "ou_xxx"}}]

        Args:
            contentJson: 飞书消息 content 字段（JSON 字符串）。
            mentions: 飞书消息 mentions 列表，可能为 None。

        Returns:
            提取的纯文本，无内容时返回空字符串。
        """
        try:
            data = json.loads(contentJson)
        except (json.JSONDecodeError, TypeError):
            return ""

        text = data.get("text", "")
        if not text:
            return ""

        # 去除 @提及占位符
        if mentions:
            for m in mentions:
                key = m.get("key", "")
                if key:
                    text = text.replace(key, "").strip()

        return text.strip()

    # ---- 信号处理 ----

    def _OnInterrupt(self, signum: int, frame: object) -> None:
        """SIGINT 信号处理器，设置 STOPPING 状态触发主循环退出。"""
        Logger.Info("FeishuChannel: received interrupt signal, stopping...")
        self._state = EChannelState.STOPPING
