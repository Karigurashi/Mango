"""Anthropic Claude Provider，底层使用 anthropic 官方 SDK。"""

from __future__ import annotations

import asyncio
import time
from typing import AsyncIterator, Iterator, Optional

import anthropic

from ..baseProvider import BaseProvider
from ..chatMessage import ChatChunk, ChatMessage, ChatResponse, TokenUsage, ToolSpec
from common.cancellationToken import CancellationToken
from ...llmConfig import LLMModel
from .anthropicProtocol import AnthropicProtocol


class AnthropicProvider(BaseProvider):
    """Anthropic Claude Messages API Provider。"""

    def __init__(self, model: LLMModel, **kwargs) -> None:
        super().__init__(model)
        self._thinkingBudget = model.thinkingBudget
        self._protocol = AnthropicProtocol()
        self._client = anthropic.Anthropic(
            base_url=self._model.url.rstrip("/"),
            api_key=self._model.apiKey,
            timeout=self._model.timeout,
            max_retries=self._model.maxRetries,
        )
        self._asyncClient = anthropic.AsyncAnthropic(
            base_url=self._model.url.rstrip("/"),
            api_key=self._model.apiKey,
            timeout=self._model.timeout,
            max_retries=self._model.maxRetries,
        )

    @property
    def ProviderName(self) -> str:
        return "anthropic"

    def Close(self) -> None:
        self._client.close()

    async def CloseAsync(self) -> None:
        await self._asyncClient.close()

    # ---- 工具绑定 ----

    def BindTools(self, tools: list[ToolSpec]) -> None:
        self._tools = tools

    # ---- TokenUsage 提取 ----

    @staticmethod
    def _ExtractUsage(usage: object) -> Optional[TokenUsage]:
        if usage is None:
            return None
        return TokenUsage(
            promptTokens=getattr(usage, "input_tokens", 0),
            completionTokens=getattr(usage, "output_tokens", 0),
            totalTokens=getattr(usage, "input_tokens", 0) + getattr(usage, "output_tokens", 0),
        )

    # ==================================================================
    #  同步 Invoke
    # ==================================================================

    def Invoke(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        maxTokens: int = 0,
        **kwargs,
    ) -> ChatResponse:
        rid = self._NewRequestId()
        t0 = time.monotonic()

        enableThinking = kwargs.pop("enableThinking", False)
        thinkingBudget = kwargs.pop("thinkingBudget", 0) or self._thinkingBudget
        enableCache = kwargs.pop("enableCache", False)

        if self._onBeforeRequest:
            self._onBeforeRequest(messages)

        try:
            params = self._protocol.BuildRequestParams(
                messages, temperature, maxTokens, stream=False,
                tools=getattr(self, "_tools", None),
                enableThinking=enableThinking, thinkingBudget=thinkingBudget,
                enableCache=enableCache,
                _modelName=self._model.modelName, **kwargs,
            )
            resp = self._client.messages.create(**params)

            textParts: list[str] = []
            thinkingParts: list[str] = []
            for block in resp.content:
                t = getattr(block, "type", "")
                if t == "text":
                    textParts.append(getattr(block, "text", ""))
                elif t == "thinking":
                    thinkingParts.append(getattr(block, "thinking", ""))

            usage = self._ExtractUsage(resp.usage)
            toolCalls = self._protocol.ParseToolCalls(resp.content)

            result = ChatResponse(
                content="\n".join(textParts),
                reasoningContent="\n".join(thinkingParts),
                model=resp.model,
                usage=usage,
                finishReason=getattr(resp, "stop_reason", "") or "",
                toolCalls=toolCalls,
            )

            self._AccumulateUsage(usage)
            self._LogSuccess(rid, "Invoke", t0, usage)

            if self._onAfterRequest:
                self._onAfterRequest(result)

            return result
        except Exception as exc:
            self._LogError(rid, "Invoke", t0, exc)
            self._RaiseLLMError(exc)

    # ==================================================================
    #  同步 Stream
    # ==================================================================

    def Stream(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        maxTokens: int = 0,
        **kwargs,
    ) -> Iterator[ChatChunk]:
        rid = self._NewRequestId()
        t0 = time.monotonic()

        enableThinking = kwargs.pop("enableThinking", False)
        thinkingBudget = kwargs.pop("thinkingBudget", 0) or self._thinkingBudget
        enableCache = kwargs.pop("enableCache", False)

        if self._onBeforeRequest:
            self._onBeforeRequest(messages)

        try:
            params = self._protocol.BuildRequestParams(
                messages, temperature, maxTokens, stream=True,
                tools=getattr(self, "_tools", None),
                enableThinking=enableThinking, thinkingBudget=thinkingBudget,
                enableCache=enableCache,
                _modelName=self._model.modelName, **kwargs,
            )
            with self._client.messages.stream(**params) as stream:
                for event in stream:
                    etype = getattr(event, "type", "")

                    if etype == "content_block_delta":
                        delta = getattr(event, "delta", None)
                        if delta is None:
                            continue
                        dt = getattr(delta, "type", "")
                        if dt == "text_delta":
                            yield ChatChunk(content=getattr(delta, "text", ""))
                        elif dt == "thinking_delta":
                            yield ChatChunk(reasoningContent=getattr(delta, "thinking", ""))

                    elif etype == "message_delta":
                        usage = self._ExtractUsage(getattr(event, "usage", None))
                        if usage:
                            self._AccumulateUsage(usage)
                        fr = getattr(getattr(event, "delta", None), "stop_reason", "")
                        yield ChatChunk(usage=usage, finishReason=fr or "")

                    elif etype == "message_stop":
                        yield ChatChunk(finishReason="end_turn")

            self._LogSuccess(rid, "Stream", t0)
        except Exception as exc:
            self._LogError(rid, "Stream", t0, exc)
            self._RaiseLLMError(exc)

    # ==================================================================
    #  异步 InvokeAsync
    # ==================================================================

    async def InvokeAsync(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        maxTokens: int = 0,
        cancellationToken: Optional[CancellationToken] = None,
        **kwargs,
    ) -> ChatResponse:
        rid = self._NewRequestId()
        t0 = time.monotonic()

        enableThinking = kwargs.pop("enableThinking", False)
        thinkingBudget = kwargs.pop("thinkingBudget", 0) or self._thinkingBudget
        enableCache = kwargs.pop("enableCache", False)

        self._CheckCancellation(cancellationToken)

        if self._onBeforeRequest:
            self._onBeforeRequest(messages)

        try:
            params = self._protocol.BuildRequestParams(
                messages, temperature, maxTokens, stream=False,
                tools=getattr(self, "_tools", None),
                enableThinking=enableThinking, thinkingBudget=thinkingBudget,
                enableCache=enableCache,
                _modelName=self._model.modelName, **kwargs,
            )
            resp = await self._InvokeWithTimeoutAsync(
                self._asyncClient.messages.create(**params),
            )

            textParts: list[str] = []
            thinkingParts: list[str] = []
            for block in resp.content:
                t = getattr(block, "type", "")
                if t == "text":
                    textParts.append(getattr(block, "text", ""))
                elif t == "thinking":
                    thinkingParts.append(getattr(block, "thinking", ""))

            usage = self._ExtractUsage(resp.usage)
            toolCalls = self._protocol.ParseToolCalls(resp.content)

            result = ChatResponse(
                content="\n".join(textParts),
                reasoningContent="\n".join(thinkingParts),
                model=resp.model,
                usage=usage,
                finishReason=getattr(resp, "stop_reason", "") or "",
                toolCalls=toolCalls,
            )

            self._AccumulateUsage(usage)
            self._LogSuccess(rid, "InvokeAsync", t0, usage)

            if self._onAfterRequest:
                self._onAfterRequest(result)

            return result
        except asyncio.CancelledError:
            self._LogCancelled(rid, "InvokeAsync")
            raise
        except Exception as exc:
            self._LogError(rid, "InvokeAsync", t0, exc)
            self._RaiseLLMError(exc)

    # ==================================================================
    #  异步 StreamAsync
    # ==================================================================

    async def StreamAsync(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        maxTokens: int = 0,
        cancellationToken: Optional[CancellationToken] = None,
        **kwargs,
    ) -> AsyncIterator[ChatChunk]:
        rid = self._NewRequestId()
        t0 = time.monotonic()

        enableThinking = kwargs.pop("enableThinking", False)
        thinkingBudget = kwargs.pop("thinkingBudget", 0) or self._thinkingBudget
        enableCache = kwargs.pop("enableCache", False)

        self._CheckCancellation(cancellationToken)

        if self._onBeforeRequest:
            self._onBeforeRequest(messages)

        try:
            params = self._protocol.BuildRequestParams(
                messages, temperature, maxTokens, stream=True,
                tools=getattr(self, "_tools", None),
                enableThinking=enableThinking, thinkingBudget=thinkingBudget,
                enableCache=enableCache,
                _modelName=self._model.modelName, **kwargs,
            )
            cancelled = False
            async with self._asyncClient.messages.stream(**params) as stream:
                async for event in stream:
                    if cancellationToken and cancellationToken.IsCancellationRequested:
                        self._LogCancelled(rid, "StreamAsync")
                        cancelled = True
                        break

                    etype = getattr(event, "type", "")

                    if etype == "content_block_delta":
                        delta = getattr(event, "delta", None)
                        if delta is None:
                            continue
                        dt = getattr(delta, "type", "")
                        if dt == "text_delta":
                            yield ChatChunk(content=getattr(delta, "text", ""))
                        elif dt == "thinking_delta":
                            yield ChatChunk(reasoningContent=getattr(delta, "thinking", ""))

                    elif etype == "message_delta":
                        usage = self._ExtractUsage(getattr(event, "usage", None))
                        if usage:
                            self._AccumulateUsage(usage)
                        fr = getattr(getattr(event, "delta", None), "stop_reason", "")
                        yield ChatChunk(usage=usage, finishReason=fr or "")

                    elif etype == "message_stop":
                        yield ChatChunk(finishReason="end_turn")

            # async with 退出时自动关闭底层 SSE 连接，服务端收到 TCP FIN 停止生成
            if not cancelled:
                self._LogSuccess(rid, "StreamAsync", t0)
        except asyncio.CancelledError:
            self._LogCancelled(rid, "StreamAsync")
            raise
        except Exception as exc:
            self._LogError(rid, "StreamAsync", t0, exc)
            self._RaiseLLMError(exc)
