"""Google Gemini Provider，底层使用 google-genai 官方 SDK。"""

from __future__ import annotations

import asyncio
import time
from typing import AsyncIterator, Iterator, Optional

from ..baseProvider import BaseProvider
from ..chatMessage import ChatChunk, ChatMessage, ChatResponse, TokenUsage, ToolSpec
from common.cancellationToken import CancellationToken
from ...llmConfig import LLMModel
from .geminiProtocol import GeminiProtocol


class GeminiProvider(BaseProvider):
    """Google Gemini Provider，封装 google-genai SDK。"""

    def __init__(self, model: LLMModel, **kwargs) -> None:
        super().__init__(model)
        self._protocol = GeminiProtocol()
        self._client = None
        self._asyncClient = None
        self._clientKwargs: dict = {
            "api_key": self._model.apiKey,
            "http_options": {
                "timeout": int(self._model.timeout * 1000),
            },
        }
        # 注：google-genai SDK 的 maxRetries 行为因版本而异，
        # 框架层通过 _InvokeWithTimeoutAsync 提供额外的超时保护

    def _GetClient(self):
        if self._client is None:
            from google import genai
            self._client = genai.Client(**self._clientKwargs)
        return self._client

    def _GetAsyncClient(self):
        if self._asyncClient is None:
            from google import genai
            self._asyncClient = genai.Client(**self._clientKwargs)
        return self._asyncClient

    @property
    def ProviderName(self) -> str:
        return "gemini"

    def Close(self) -> None:
        pass  # genai Client 无显式 close

    async def CloseAsync(self) -> None:
        pass

    # ---- 工具绑定 ----

    def BindTools(self, tools: list[ToolSpec]) -> None:
        self._tools = tools

    # ---- TokenUsage 提取 ----

    @staticmethod
    def _ExtractUsage(usageMetadata: object) -> Optional[TokenUsage]:
        if usageMetadata is None:
            return None
        return TokenUsage(
            promptTokens=getattr(usageMetadata, "prompt_token_count", 0),
            completionTokens=getattr(usageMetadata, "candidates_token_count", 0),
            totalTokens=getattr(usageMetadata, "total_token_count", 0),
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

        if self._onBeforeRequest:
            self._onBeforeRequest(messages)

        try:
            params = self._protocol.BuildRequestParams(
                messages, temperature, maxTokens, stream=False,
                tools=getattr(self, "_tools", None),
                _modelName=self._model.modelName, **kwargs,
            )
            model = params.pop("model")
            config = params.pop("config", {})
            contents = params.pop("contents")

            resp = self._GetClient().models.generate_content(
                model=model, contents=contents, config=config,
            )

            text = resp.text or ""
            usage = self._ExtractUsage(getattr(resp, "usage_metadata", None))
            toolCalls = self._protocol.ParseToolCalls(getattr(resp, "candidates", []))

            result = ChatResponse(
                content=text,
                model=self._model.modelName,
                usage=usage,
                finishReason=str(getattr(getattr(resp, "candidates", [{}])[0], "finish_reason", "")) if getattr(resp, "candidates", None) else "",
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

        if self._onBeforeRequest:
            self._onBeforeRequest(messages)

        try:
            params = self._protocol.BuildRequestParams(
                messages, temperature, maxTokens, stream=True,
                tools=getattr(self, "_tools", None),
                _modelName=self._model.modelName, **kwargs,
            )
            model = params.pop("model")
            config = params.pop("config", {})
            contents = params.pop("contents")

            stream = self._GetClient().models.generate_content_stream(
                model=model, contents=contents, config=config,
            )

            for chunk in stream:
                text = chunk.text or ""
                usage = self._ExtractUsage(getattr(chunk, "usage_metadata", None))
                if usage:
                    self._AccumulateUsage(usage)

                cc = ChatChunk(content=text, usage=usage)
                if not cc.isEmpty:
                    yield cc

            self._LogSuccess(rid, "Stream", t0, self._totalUsage)
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

        self._CheckCancellation(cancellationToken)

        if self._onBeforeRequest:
            self._onBeforeRequest(messages)

        try:
            params = self._protocol.BuildRequestParams(
                messages, temperature, maxTokens, stream=False,
                tools=getattr(self, "_tools", None),
                _modelName=self._model.modelName, **kwargs,
            )
            model = params.pop("model")
            config = params.pop("config", {})
            contents = params.pop("contents")

            resp = await self._InvokeWithTimeoutAsync(
                self._GetAsyncClient().aio.models.generate_content(
                    model=model, contents=contents, config=config,
                ),
            )

            text = resp.text or ""
            usage = self._ExtractUsage(getattr(resp, "usage_metadata", None))
            toolCalls = self._protocol.ParseToolCalls(getattr(resp, "candidates", []))

            result = ChatResponse(
                content=text,
                model=self._model.modelName,
                usage=usage,
                finishReason=str(getattr(getattr(resp, "candidates", [{}])[0], "finish_reason", "")) if getattr(resp, "candidates", None) else "",
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

        self._CheckCancellation(cancellationToken)

        if self._onBeforeRequest:
            self._onBeforeRequest(messages)

        try:
            params = self._protocol.BuildRequestParams(
                messages, temperature, maxTokens, stream=True,
                tools=getattr(self, "_tools", None),
                _modelName=self._model.modelName, **kwargs,
            )
            model = params.pop("model")
            config = params.pop("config", {})
            contents = params.pop("contents")

            stream = None
            cancelled = False
            try:
                stream = await self._GetAsyncClient().aio.models.generate_content_stream(
                    model=model, contents=contents, config=config,
                )

                async for chunk in stream:
                    if cancellationToken and cancellationToken.IsCancellationRequested:
                        self._LogCancelled(rid, "StreamAsync")
                        cancelled = True
                        break

                    text = chunk.text or ""
                    usage = self._ExtractUsage(getattr(chunk, "usage_metadata", None))
                    if usage:
                        self._AccumulateUsage(usage)

                    cc = ChatChunk(content=text, usage=usage)
                    if not cc.isEmpty:
                        yield cc

                if not cancelled:
                    self._LogSuccess(rid, "StreamAsync", t0, self._totalUsage)
            finally:
                # 主动关闭底层 gRPC 流，通知服务端取消生成
                if stream is not None and hasattr(stream, 'aclose'):
                    await stream.aclose()
        except asyncio.CancelledError:
            self._LogCancelled(rid, "StreamAsync")
            raise
        except Exception as exc:
            self._LogError(rid, "StreamAsync", t0, exc)
            self._RaiseLLMError(exc)
