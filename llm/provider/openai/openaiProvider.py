"""OpenAI 兼容 Provider，底层使用 openai 官方 SDK。

支持 GPT-4 / GPT-3.5 / DeepSeek / Ollama / vLLM 等所有
兼容 /chat/completions 协议的端点。
"""

from __future__ import annotations

import asyncio
import time
from typing import AsyncIterator, Iterator, Optional

import openai

from ..baseProvider import BaseProvider
from ..chatMessage import ChatChunk, ChatMessage, ChatResponse, TokenUsage, ToolSpec
from common.cancellationToken import CancellationToken
from ...llmConfig import LLMModel
from ...llmRequestParams import LLMRequestParams
from .openaiProtocol import OpenAIProtocol


class OpenAIProvider(BaseProvider):
    """OpenAI 兼容 Provider，封装 openai 官方 SDK。"""

    def __init__(self, model: LLMModel, **kwargs) -> None:
        super().__init__(model)
        self._protocol = OpenAIProtocol()
        self._client = openai.OpenAI(
            base_url=self._model.url.rstrip("/"),
            api_key=self._model.apiKey,
            timeout=self._model.timeout,
            max_retries=self._model.maxRetries,
        )
        self._asyncClient = openai.AsyncOpenAI(
            base_url=self._model.url.rstrip("/"),
            api_key=self._model.apiKey,
            timeout=self._model.timeout,
            max_retries=self._model.maxRetries,
        )

    @property
    def ProviderName(self) -> str:
        return "openai"

    def Close(self) -> None:
        self._client.close()

    async def CloseAsync(self) -> None:
        await self._asyncClient.close()

    # ---- TokenUsage 提取 ----

    @staticmethod
    def _ExtractUsage(usage: object) -> Optional[TokenUsage]:
        if usage is None:
            return None
        return TokenUsage(
            promptTokens=getattr(usage, "prompt_tokens", 0),
            completionTokens=getattr(usage, "completion_tokens", 0),
            totalTokens=getattr(usage, "total_tokens", 0),
        )

    # ---- reasoning_content 提取 ----

    @staticmethod
    def _ExtractReasoning(message: object) -> str:
        extra = getattr(message, "model_extra", None) or {}
        return extra.get("reasoning_content", "") or ""

    # ==================================================================
    #  同步 Invoke
    # ==================================================================

    def Invoke(
        self,
        messages: list[ChatMessage],
        requestParams: Optional[LLMRequestParams] = None,
    ) -> ChatResponse:
        rid = self._NewRequestId()
        t0 = time.monotonic()

        rp = requestParams or LLMRequestParams.DEFAULT

        if rp.onBeforeRequest:
            rp.onBeforeRequest(messages)

        try:
            params = self._protocol.BuildRequestParams(
                messages, rp, stream=False,
                tools=rp.tools,
                modelName=self._model.modelName,
            )
            resp = self._client.chat.completions.create(**params)

            choice = resp.choices[0]
            content = choice.message.content or ""
            reasoningContent = self._ExtractReasoning(choice.message)
            usage = self._ExtractUsage(resp.usage)
            toolCalls = self._protocol.ParseToolCalls(choice)

            result = ChatResponse(
                content=content,
                reasoningContent=reasoningContent,
                model=resp.model or self._model.modelName,
                usage=usage,
                finishReason=choice.finish_reason or "",
                toolCalls=toolCalls,
            )

            self._AccumulateUsage(usage)
            self._LogSuccess(rid, "Invoke", t0, usage)

            if rp.onAfterRequest:
                rp.onAfterRequest(result)

            return result
        except Exception as exc:
            self._LogError(rid, "Invoke", t0, exc)
            self._RaiseLLMError(exc, onError=rp.onError)

    # ==================================================================
    #  同步 Stream
    # ==================================================================

    def Stream(
        self,
        messages: list[ChatMessage],
        requestParams: Optional[LLMRequestParams] = None,
    ) -> Iterator[ChatChunk]:
        rid = self._NewRequestId()
        t0 = time.monotonic()

        rp = requestParams or LLMRequestParams.DEFAULT

        if rp.onBeforeRequest:
            rp.onBeforeRequest(messages)

        try:
            params = self._protocol.BuildRequestParams(
                messages, rp, stream=True,
                tools=rp.tools,
                modelName=self._model.modelName,
            )
            stream = self._client.chat.completions.create(**params)

            for chunk in stream:
                usage = None
                if getattr(chunk, "usage", None) is not None:
                    usage = self._ExtractUsage(chunk.usage)
                    self._AccumulateUsage(usage)

                if not chunk.choices:
                    if usage:
                        yield ChatChunk(usage=usage)
                    continue

                choice = chunk.choices[0]
                delta = choice.delta
                content = delta.content or "" if delta else ""
                reasoningContent = self._ExtractReasoning(delta) if delta else ""

                cc = ChatChunk(
                    content=content,
                    reasoningContent=reasoningContent,
                    usage=usage,
                    finishReason=choice.finish_reason or "",
                    index=choice.index or 0,
                )
                if not cc.isEmpty:
                    yield cc

            self._LogSuccess(rid, "Stream", t0, self._totalUsage)
        except Exception as exc:
            self._LogError(rid, "Stream", t0, exc)
            self._RaiseLLMError(exc, onError=rp.onError)

    # ==================================================================
    #  异步 InvokeAsync
    # ==================================================================

    async def InvokeAsync(
        self,
        messages: list[ChatMessage],
        cancellationToken: Optional[CancellationToken] = None,
        requestParams: Optional[LLMRequestParams] = None,
    ) -> ChatResponse:
        rid = self._NewRequestId()
        t0 = time.monotonic()

        rp = requestParams or LLMRequestParams.DEFAULT

        self._CheckCancellation(cancellationToken)

        if rp.onBeforeRequest:
            rp.onBeforeRequest(messages)

        try:
            params = self._protocol.BuildRequestParams(
                messages, rp, stream=False,
                tools=rp.tools,
                modelName=self._model.modelName,
            )
            resp = await self._InvokeWithTimeoutAsync(
                self._asyncClient.chat.completions.create(**params),
            )

            choice = resp.choices[0]
            content = choice.message.content or ""
            reasoningContent = self._ExtractReasoning(choice.message)
            usage = self._ExtractUsage(resp.usage)
            toolCalls = self._protocol.ParseToolCalls(choice)

            result = ChatResponse(
                content=content,
                reasoningContent=reasoningContent,
                model=resp.model or self._model.modelName,
                usage=usage,
                finishReason=choice.finish_reason or "",
                toolCalls=toolCalls,
            )

            self._AccumulateUsage(usage)
            self._LogSuccess(rid, "InvokeAsync", t0, usage)

            if rp.onAfterRequest:
                rp.onAfterRequest(result)

            return result
        except asyncio.CancelledError:
            self._LogCancelled(rid, "InvokeAsync")
            raise
        except Exception as exc:
            self._LogError(rid, "InvokeAsync", t0, exc)
            self._RaiseLLMError(exc, onError=rp.onError)

    # ==================================================================
    #  异步 StreamAsync
    # ==================================================================

    async def StreamAsync(
        self,
        messages: list[ChatMessage],
        cancellationToken: Optional[CancellationToken] = None,
        requestParams: Optional[LLMRequestParams] = None,
    ) -> AsyncIterator[ChatChunk]:
        rid = self._NewRequestId()
        t0 = time.monotonic()

        rp = requestParams or LLMRequestParams.DEFAULT

        self._CheckCancellation(cancellationToken)

        if rp.onBeforeRequest:
            rp.onBeforeRequest(messages)

        try:
            stream = None
            cancelled = False
            try:
                params = self._protocol.BuildRequestParams(
                    messages, rp, stream=True,
                    tools=rp.tools,
                    modelName=self._model.modelName,
                )
                stream = await self._asyncClient.chat.completions.create(**params)

                async for chunk in stream:
                    if cancellationToken and cancellationToken.IsCancellationRequested:
                        self._LogCancelled(rid, "StreamAsync")
                        cancelled = True
                        break

                    usage = None
                    if getattr(chunk, "usage", None) is not None:
                        usage = self._ExtractUsage(chunk.usage)
                        self._AccumulateUsage(usage)

                    if not chunk.choices:
                        if usage:
                            yield ChatChunk(usage=usage)
                        continue

                    choice = chunk.choices[0]
                    delta = choice.delta
                    content = delta.content or "" if delta else ""
                    reasoningContent = self._ExtractReasoning(delta) if delta else ""

                    cc = ChatChunk(
                        content=content,
                        reasoningContent=reasoningContent,
                        usage=usage,
                        finishReason=choice.finish_reason or "",
                        index=choice.index or 0,
                    )
                    if not cc.isEmpty:
                        yield cc

                if not cancelled:
                    self._LogSuccess(rid, "StreamAsync", t0, self._totalUsage)
            finally:
                # 主动关闭底层 HTTP 连接，确保服务端收到 TCP RST 立即停止生成
                if stream is not None:
                    await stream.close()
        except asyncio.CancelledError:
            self._LogCancelled(rid, "StreamAsync")
            raise
        except Exception as exc:
            self._LogError(rid, "StreamAsync", t0, exc)
            self._RaiseLLMError(exc, onError=rp.onError)
