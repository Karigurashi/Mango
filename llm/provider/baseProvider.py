"""Provider 抽象基类。

连接池、重试、超时由官方 SDK 接管，框架层额外提供：
- CancellationToken 取消机制
- asyncio.wait_for 超时包装（双重保险）
- asyncio.CancelledError 清理处理
- 回调钩子、Token 累计、结构化日志。
"""

from __future__ import annotations

import asyncio
import time
import uuid
from abc import abstractmethod
from typing import Callable, Optional

from common.llmError import LLMError
from common.logger import Logger

from ..baseLLM import BaseLLM
from common.cancellationToken import CancellationToken
from ..eTier import ETier
from ..llmConfig import LLMModel
from .chatMessage import ChatMessage, ChatResponse, TokenUsage


class BaseProvider(BaseLLM):
    """Provider 抽象基类。

    子类负责对接具体 SDK（openai / anthropic / gemini），
    实现 Invoke / Stream / InvokeAsync / StreamAsync。
    """

    def __init__(self, model: LLMModel) -> None:
        self._model = model

        # 累计用量
        self._totalUsage = TokenUsage()

        # 回调钩子
        self._onBeforeRequest: Optional[Callable[[list[ChatMessage]], None]] = None
        self._onAfterRequest: Optional[Callable[[ChatResponse], None]] = None
        self._onError: Optional[Callable[[Exception], None]] = None

    # ———— 元信息 ————
    @property
    @abstractmethod
    def ProviderName(self) -> str:
        """Provider 标识，如 'openai'、'anthropic'。"""
        ...

    @property
    def ModelName(self) -> str:
        return self._model.modelName

    @property
    def Tier(self) -> ETier:
        return self._model.tier

    # ———— 资源清理 ————
    def Close(self) -> None:
        """关闭底层 SDK 客户端（同步）。"""
        pass

    async def CloseAsync(self) -> None:
        """关闭底层 SDK 客户端（异步）。"""
        pass

    # ———— 回调注册 ————
    def OnBeforeRequest(self, callback: Callable[[list[ChatMessage]], None]) -> None:
        self._onBeforeRequest = callback

    def OnAfterRequest(self, callback: Callable[[ChatResponse], None]) -> None:
        self._onAfterRequest = callback

    def OnError(self, callback: Callable[[Exception], None]) -> None:
        self._onError = callback

    # ———— Token 累计 ————
    @property
    def TotalUsage(self) -> TokenUsage:
        return self._totalUsage

    def ResetUsage(self) -> None:
        self._totalUsage = TokenUsage()

    def _AccumulateUsage(self, usage: Optional[TokenUsage]) -> None:
        if usage:
            self._totalUsage = self._totalUsage + usage

    # ———— 结构化日志 ————
    @staticmethod
    def _NewRequestId() -> str:
        return uuid.uuid4().hex[:8]

    def _LogSuccess(
        self, rid: str, method: str, t0: float, usage: Optional[TokenUsage] = None,
    ) -> None:
        dur = int((time.monotonic() - t0) * 1000)
        prompt = usage.promptTokens if usage else 0
        completion = usage.completionTokens if usage else 0
        Logger.Info(
            "rid=%s %s %s/%s dur=%dms tokens_in=%d tokens_out=%d",
            rid, method, self.ProviderName, self._model.modelName,
            dur, prompt, completion,
        )

    def _LogError(
        self, rid: str, method: str, t0: float, exc: Exception,
    ) -> None:
        dur = int((time.monotonic() - t0) * 1000)
        Logger.Error(
            "rid=%s %s %s/%s dur=%dms error=%s",
            rid, method, self.ProviderName, self._model.modelName,
            dur, str(exc)[:200],
        )

    def _RaiseLLMError(self, exc: Exception) -> None:
        """统一转换为 LLMError。"""
        if self._onError:
            self._onError(exc)
        raise LLMError(
            str(exc),
            provider=self.ProviderName, model=self._model.modelName,
        ) from exc

    # ———— 取消检查与超时包装 ————

    @staticmethod
    def _CheckCancellation(token: Optional[CancellationToken]) -> None:
        """检查取消令牌，若已取消则抛出 LLMError。"""
        if token is not None and token.IsCancellationRequested:
            raise LLMError("Request cancelled by CancellationToken")

    async def _InvokeWithTimeoutAsync(self, coro, timeout: Optional[float] = None) -> object:
        """用 asyncio.wait_for 包装异步调用，超时抛出 LLMError。

        与 SDK 内置 timeout 形成双重保险：SDK timeout 控制单次 HTTP 请求，
        本层 timeout 控制整个调用生命周期（含重试时间）。
        """
        timeout = timeout if timeout is not None else self._model.timeout
        try:
            return await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            raise LLMError(
                f"Request timed out after {timeout}s",
                provider=self.ProviderName, model=self._model.modelName,
            )

    @staticmethod
    def _LogCancelled(rid: str, method: str) -> None:
        """记录取消事件日志。"""
        Logger.Info("rid=%s %s CANCELLED by token", rid, method)
