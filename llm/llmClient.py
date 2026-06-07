"""LLM 模型客户端，面向用户的统一调用入口。

每个 LLMClient 引用 Manager 中的共享 Provider 实例，
支持消息归一化、工具绑定、KV-Cache、档位感知。
"""

from __future__ import annotations

from typing import AsyncIterator, Iterator, Optional, Union

from .baseLLM import BaseLLM
from common.cancellationToken import CancellationToken
from .provider.chatMessage import ChatChunk, ChatMessage, ChatResponse, TokenUsage, ToolSpec
from .eTier import ETier

# 消息输入类型：裸字符串 → list[dict] → list[ChatMessage] 三档
MessageInput = Union[str, list[dict[str, str]], list[ChatMessage]]


class LLMClient:
    """模型客户端，封装单个 LLM 的调用与配置。

    使用方式::

        client = manager.GetClient("gpt-4")
        response = client.Invoke("Hello")
        print(response.content)
    """

    def __init__(self, provider: BaseLLM) -> None:
        self._provider = provider
        self._enableCache = False

    # ---- 元信息 ----

    @property
    def ModelName(self) -> str:
        return self._provider.ModelName

    @property
    def ProviderName(self) -> str:
        return self._provider.ProviderName

    @property
    def Tier(self) -> ETier:
        return self._provider.Tier

    # ---- 消息归一化 ----

    @staticmethod
    def _NormalizeMessages(messages: MessageInput) -> list[ChatMessage]:
        """str → dict 列表 → ChatMessage 列表，三级自动归一。"""
        if isinstance(messages, str):
            return [ChatMessage.User(messages)]
        if not messages:
            return []
        if isinstance(messages[0], ChatMessage):
            return messages  # type: ignore[return-value]
        return [ChatMessage(role=m["role"], content=m["content"]) for m in messages]  # type: ignore[arg-type]

    # ---- 四维调用 ----

    def Invoke(
        self,
        messages: MessageInput,
        temperature: float = 0.7,
        maxTokens: int = 0,
        **kwargs,
    ) -> ChatResponse:
        """同步非流式调用。"""
        if self._enableCache:
            kwargs.setdefault("enableCache", True)
        return self._provider.Invoke(
            self._NormalizeMessages(messages), temperature, maxTokens, **kwargs,
        )

    def Stream(
        self,
        messages: MessageInput,
        temperature: float = 0.7,
        maxTokens: int = 0,
        **kwargs,
    ) -> Iterator[ChatChunk]:
        """同步流式调用。"""
        if self._enableCache:
            kwargs.setdefault("enableCache", True)
        return self._provider.Stream(
            self._NormalizeMessages(messages), temperature, maxTokens, **kwargs,
        )

    async def InvokeAsync(
        self,
        messages: MessageInput,
        temperature: float = 0.7,
        maxTokens: int = 0,
        cancellationToken: Optional[CancellationToken] = None,
        **kwargs,
    ) -> ChatResponse:
        """异步非流式调用，支持通过 CancellationToken 取消。"""
        if self._enableCache:
            kwargs.setdefault("enableCache", True)
        return await self._provider.InvokeAsync(
            self._NormalizeMessages(messages), temperature, maxTokens,
            cancellationToken=cancellationToken, **kwargs,
        )

    async def StreamAsync(
        self,
        messages: MessageInput,
        temperature: float = 0.7,
        maxTokens: int = 0,
        cancellationToken: Optional[CancellationToken] = None,
        **kwargs,
    ) -> AsyncIterator[ChatChunk]:
        """异步流式调用，支持通过 CancellationToken 在 chunk 间取消。"""
        if self._enableCache:
            kwargs.setdefault("enableCache", True)
        async for chunk in self._provider.StreamAsync(
            self._NormalizeMessages(messages), temperature, maxTokens,
            cancellationToken=cancellationToken, **kwargs,
        ):
            yield chunk

    # ---- 工具绑定 ----

    def BindTools(self, tools: list[ToolSpec]) -> None:
        """绑定工具列表，后续调用自动携带。"""
        self._provider.BindTools(tools)

    # ---- KV-Cache ----

    def EnableCache(self, enable: bool) -> None:
        """开关 KV-Cache（Anthropic Prompt Caching）。"""
        self._enableCache = enable

    # ---- 用量查询 ----

    def GetUsage(self) -> TokenUsage:
        """查询累计 Token 用量。"""
        return self._provider.TotalUsage

    def ResetUsage(self) -> None:
        """重置累计用量。"""
        self._provider.ResetUsage()
