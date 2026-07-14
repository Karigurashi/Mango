"""FeishuCardComponent —— 飞书流式卡片组件，独立线程消费 Agent 事件。

通过 queue.Queue 解耦 Agent 推理（群线程）与卡片 HTTP 更新（消费线程）。
群线程 OnAgentEventSync 调用 HandleEvent 将事件入队（纳秒级，不阻塞推理）。
消费线程独立运行事件循环，负责节流、构建卡片 JSON、调用飞书 API。

线程模型::

    Group 线程（Agent 事件循环）         消费线程（卡片 I/O）
    ┌─────────────────────┐           ┌──────────────────────┐
    │ agent.RunStreamAsync │           │ while True:          │
    │  → 产出事件          │           │   item = queue.get() │
    │  → OnAgentEventSync  │           │   → 更新 _TurnState  │
    │  → queue.put_nowait  │──事件队列──→│   → 节流判断 0.3s    │
    │  → 立即返回，继续推理 │           │   → _BuildCardJson   │
    └─────────────────────┘           │   → await HTTP PATCH  │
                                      └──────────────────────┘
"""

from __future__ import annotations

import asyncio
import json
import queue
import threading
import time
from typing import TYPE_CHECKING, Optional

from agent import AgentStreamEvent, EAgentStreamEventType
from common.logger import Logger

from ..channel import IChannelComponent

if TYPE_CHECKING:
    from .feishuApi import FeishuApi
    from .feishuChannel import FeishuChannel

_THROTTLE_INTERVAL: float = 0.3


class _TurnState:
    """单轮 Agent 对话状态累积器（内部类，不导出）。

    Attributes:
        thinking: 累积的思考内容。
        toolCalls: 格式化的工具调用描述列表。
        text: 累积的文本输出。
        hasError: 是否发生错误。
        error: 错误信息。
    """

    def __init__(self) -> None:
        self.thinking: str = ""
        self.toolCalls: list[str] = []
        self.text: str = ""
        self.hasError: bool = False
        self.error: str = ""


class _CardSession:
    """流式卡片会话（内部类，不导出）。

    跟踪单个群组一次 Agent 运行周期内的卡片消息状态。

    Attributes:
        state: 对话状态累积器。
        messageId: 已发送卡片的 message_id，初始为空。
        initialSent: 初始卡片是否已发送。
        lastUpdateTime: 上次 HTTP 更新的单调时间戳。
    """

    def __init__(self) -> None:
        self.state: _TurnState = _TurnState()
        self.messageId: str = ""
        self.initialSent: bool = False
        self.lastUpdateTime: float = 0.0


class FeishuCardComponent(IChannelComponent):
    """飞书流式卡片组件 —— 独立线程消费 Agent 事件，HTTP 更新卡片。

    由 FeishuChannel 在 __init__ 中创建并初始化。
    主线程通过 HandleEvent 将事件入队，消费线程异步处理卡片发送与更新。

    用法::

        channel = FeishuChannel(config)
        # FeishuChannel.__init__ 内部:
        #   self._cardComponent = FeishuCardComponent()
        #   self._cardComponent.OnInitialize(self)
        #
        # OnAgentEventSync 中:
        #   self._cardComponent.HandleEvent(groupId, event)
    """

    def __init__(self) -> None:
        self._channel: Optional[FeishuChannel] = None
        self._api: Optional[FeishuApi] = None
        self._queue: queue.Queue = queue.Queue()
        self._cardSessions: dict[str, _CardSession] = {}
        self._consumerThread: Optional[threading.Thread] = None
        self._consumerLoop: Optional[asyncio.AbstractEventLoop] = None

    # ---- IChannelComponent 生命周期 ----

    def OnInitialize(self, channel: FeishuChannel) -> None:
        """初始化组件，获取 API 引用并启动消费线程。"""
        self._channel = channel
        self._api = channel._api
        self._consumerThread = threading.Thread(
            target=self._RunConsumer,
            name="feishu-card",
            daemon=True,
        )
        self._consumerThread.start()

    def OnDestroy(self) -> None:
        """通知消费线程关闭并等待退出。"""
        self._queue.put(None)
        if self._consumerThread is not None:
            self._consumerThread.join(timeout=5.0)
            self._consumerThread = None
        self._cardSessions.clear()

    # ---- 生产者入口（主线程调用） ----

    def HandleEvent(self, groupId: str, event: AgentStreamEvent) -> None:
        """将 Agent 事件入队（主线程调用，纳秒级，不阻塞推理）。

        Args:
            groupId: 事件来源群组 ID。
            event: Agent 流式事件。
        """
        self._queue.put_nowait((groupId, event))

    # ---- 消费者线程 ----

    def _RunConsumer(self) -> None:
        """消费线程入口，创建独立事件循环并运行。"""
        self._consumerLoop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._consumerLoop)
        try:
            self._consumerLoop.run_until_complete(self._ConsumerLoopAsync())
        except Exception as exc:
            Logger.Error(f"FeishuCardComponent consumer crashed: {exc}")
        finally:
            self._consumerLoop.close()

    async def _ConsumerLoopAsync(self) -> None:
        """消费者主循环：从队列取事件，处理卡片更新。"""
        loop = asyncio.get_running_loop()
        while True:
            item = await loop.run_in_executor(None, self._queue.get)
            if item is None:
                break
            groupId, event = item
            try:
                await self._ProcessEventAsync(groupId, event)
            except Exception as exc:
                Logger.Error(f"FeishuCardComponent process event failed: {exc}")

    async def _ProcessEventAsync(
        self,
        groupId: str,
        event: AgentStreamEvent,
    ) -> None:
        """处理单个 Agent 事件，更新状态并发送/更新卡片。

        Args:
            groupId: 事件来源群组 ID。
            event: Agent 流式事件。
        """
        session = self._cardSessions.get(groupId)
        if session is None:
            session = _CardSession()
            self._cardSessions[groupId] = session

        if event.eventType == EAgentStreamEventType.TURN_START:
            if not session.initialSent:
                session.initialSent = True
                cardJson = self._BuildCardJson(session.state, streaming=True)
                messageId = await self._api.SendCardAsync(groupId, cardJson)  # type: ignore[union-attr]
                session.messageId = messageId
                session.lastUpdateTime = time.monotonic()

        elif event.eventType == EAgentStreamEventType.THINKING_COMPLETE:
            if event.content:
                session.state.thinking += event.content + "\n\n"
            await self._ThrottledUpdate(session)

        elif event.eventType == EAgentStreamEventType.TOOL_START:
            briefArgs = self._BriefJson(event.toolArgs)
            session.state.toolCalls.append(f"`{event.toolName}` {briefArgs}")
            await self._ThrottledUpdate(session)

        elif event.eventType == EAgentStreamEventType.TOOL_RESULT:
            if session.state.toolCalls:
                briefResult = self._BriefText(event.content)
                session.state.toolCalls[-1] += f" → {briefResult}"
            await self._ThrottledUpdate(session)

        elif event.eventType == EAgentStreamEventType.TEXT_DELTA:
            session.state.text += event.content
            await self._ThrottledUpdate(session)

        elif event.eventType == EAgentStreamEventType.ERROR:
            session.state.hasError = True
            session.state.error = event.error
            await self._ThrottledUpdate(session)

        elif event.eventType == EAgentStreamEventType.DONE:
            cardJson = self._BuildCardJson(session.state, streaming=False)
            if session.messageId:
                await self._api.UpdateCardAsync(session.messageId, cardJson)  # type: ignore[union-attr]
            else:
                await self._api.SendCardAsync(groupId, cardJson)  # type: ignore[union-attr]
            self._cardSessions.pop(groupId, None)

    async def _ThrottledUpdate(self, session: _CardSession) -> None:
        """节流更新：距上次更新不足 _THROTTLE_INTERVAL 则跳过。

        Args:
            session: 当前群组的卡片会话。
        """
        if not session.messageId:
            return
        now = time.monotonic()
        if now - session.lastUpdateTime < _THROTTLE_INTERVAL:
            return
        session.lastUpdateTime = now
        cardJson = self._BuildCardJson(session.state, streaming=True)
        await self._api.UpdateCardAsync(session.messageId, cardJson)  # type: ignore[union-attr]

    # ---- 卡片构建 ----

    @staticmethod
    def _BuildCardJson(state: _TurnState, streaming: bool = False) -> str:
        """根据累积的对话状态构建飞书卡片 JSON（schema 2.0）。

        Args:
            state: 单轮对话累积状态。
            streaming: 是否为流式更新中（添加状态指示器）。

        Returns:
            飞书卡片 JSON 字符串。
        """
        elements: list[dict] = []

        # 思考过程
        if state.thinking:
            thinkingText = state.thinking.strip()
            if len(thinkingText) > 1500:
                thinkingText = thinkingText[:1500] + "..."
            elements.append({
                "tag": "markdown",
                "content": f"💭 **思考过程**\n\n> {thinkingText.replace(chr(10), chr(10) + '> ')}",
            })
            elements.append({"tag": "hr"})

        # 工具调用
        if state.toolCalls:
            toolLines = []
            for i, call in enumerate(state.toolCalls, 1):
                toolLines.append(f"{i}. {call}")
            elements.append({
                "tag": "markdown",
                "content": "🔧 **工具调用**\n\n" + "\n".join(toolLines),
            })
            elements.append({"tag": "hr"})

        # 正文回复
        if state.text:
            elements.append({
                "tag": "markdown",
                "content": state.text.strip(),
            })

        # 错误信息
        if state.hasError:
            if elements and elements[-1].get("tag") != "hr":
                elements.append({"tag": "hr"})
            elements.append({
                "tag": "markdown",
                "content": f"❌ **错误**: {state.error}",
            })

        # 空内容兜底
        if not elements:
            elements.append({
                "tag": "markdown",
                "content": "⏳ 正在处理..." if streaming else "_(无输出)_",
            })

        # 流式状态指示
        if streaming and elements:
            elements.append({"tag": "hr"})
            elements.append({
                "tag": "markdown",
                "content": "⏳ _正在生成..._",
            })

        card = {
            "schema": "2.0",
            "header": {
                "title": {"tag": "plain_text", "content": "🤖 Agent ⏳" if streaming else "🤖 Agent"},
                "template": "turquoise" if streaming else "blue",
            },
            "body": {"elements": elements},
        }
        return json.dumps(card, ensure_ascii=False)

    @staticmethod
    def _BriefJson(data: Optional[dict], maxLen: int = 120) -> str:
        """将字典截断为简短的 JSON 字符串。

        Args:
            data: 原始字典，None 时返回空字符串。
            maxLen: 最大字符数。

        Returns:
            截断后的 JSON 字符串。
        """
        if not data:
            return ""
        text = json.dumps(data, ensure_ascii=False)
        if len(text) > maxLen:
            return text[:maxLen] + "..."
        return text

    @staticmethod
    def _BriefText(text: str, maxLen: int = 150) -> str:
        """截断文本到指定长度，替换换行符为空格。

        Args:
            text: 原始文本。
            maxLen: 最大字符数。

        Returns:
            截断后的单行文本。
        """
        if not text:
            return ""
        text = text.replace("\n", " ").strip()
        if len(text) > maxLen:
            return text[:maxLen] + "..."
        return text
