"""LLMComponent —— 将 BaseLLM 封装为可挂载的 IComponent。

挂载到 BaseAgent 后，通过 BaseAgent.GetComponent(LLMComponent) 获取 LLM 实例、
工具绑定、用量追踪和四维调用能力。

重试机制已下沉至 llm/provider/BaseProvider 层，
LLMComponent 仅做透明代理，不再包含任何重试逻辑。
"""

from __future__ import annotations

from typing import AsyncIterator, Iterator, Optional, TYPE_CHECKING, Union

from agent.component.data import dataComponent
from agent.core.baseComponent import IComponent
from common.cancellationToken import CancellationToken
from llm.baseLLM import BaseLLM
from llm.llmRequestParams import LLMRequestParams
from llm.provider.chatMessage import ChatChunk, ChatMessage, ChatResponse, TokenUsage, ToolSpec
from llm.tokenEstimator import TokenEstimator

if TYPE_CHECKING:
    from agent.core.baseAgent import BaseAgent

# 消息输入类型：裸字符串 → list[dict] → list[ChatMessage] 三档
MessageInput = Union[str, list[dict[str, str]], list[ChatMessage]]


class LLMComponent(IComponent):
    """LLM 组件 —— 持有 BaseLLM、工具绑定、用量追踪和四维调用。

    挂载到 BaseAgent 后自动可用，卸载时清理状态。

    用法::

        agent = BaseAgent()
        llmComp = agent.AddComponent(LLMComponent)
        llmComp.llm = someBaseLLM
        response = llmComp.Invoke("Hello")
    """

    def __init__(self) -> None:
        self._llm: BaseLLM | None = None
        self._requestParams = LLMRequestParams()
        self._tokenEstimator = TokenEstimator()  # 实例级隔离，多 Agent 互不干扰

    # ---- 生命周期 ----

    def OnInitialize(self, agent: BaseAgent) -> None:
        """挂载后初始化 TokenEstimator。"""
        dataComponent = agent.GetComponent(dataComponent)

        self._llm = dataComponent.llm
        self._tokenEstimator.Configure(modelName=self._llm.ModelName)

    def OnDestroy(self) -> None:
        """从 BaseAgent 卸载时回调。"""
        pass

    # ---- 属性 ----

    @property
    def llm(self) -> BaseLLM:
        """获取底层 BaseLLM 实例，未初始化时抛出 RuntimeError。"""
        if self._llm is None:
            raise RuntimeError("LLMComponent.llm has not been initialized. Ensure Agent is constructed with a valid BaseLLM.")
        return self._llm

    @llm.setter
    def llm(self, value: BaseLLM) -> None:
        self._llm = value

    @property
    def TokenEstimatorInstance(self) -> TokenEstimator:
        """获取本组件持有的独立 TokenEstimator 实例。"""
        return self._tokenEstimator

    # ---- 元信息 ----

    @property
    def ModelName(self) -> str:
        return self._llm.ModelName

    @property
    def ProviderName(self) -> str:
        return self._llm.ProviderName

    # ---- 工具绑定 ----

    @property
    def RequestParams(self) -> LLMRequestParams:
        """当前请求参数（含工具列表）。"""
        return self._requestParams

    def BindTools(self, tools: list[ToolSpec]) -> None:
        """绑定工具列表，直接修改原始对象。"""
        self._requestParams.tools = tools if tools else None

    # ---- 用量追踪 ----

    def GetUsage(self) -> TokenUsage:
        """查询累计 Token 用量。"""
        return self._llm.TotalUsage

    def ResetUsage(self) -> None:
        """重置累计用量。"""
        self._llm.ResetUsage()

    # ---- 消息归一化（三个明确签名，禁止 isinstance 分支） ----

    @staticmethod
    def FromStr(text: str) -> list[ChatMessage]:
        """从裸字符串构造单条 User 消息。"""
        return [ChatMessage.User(text)]

    @staticmethod
    def FromDicts(dicts: list[dict[str, str]]) -> list[ChatMessage]:
        """从 dict 列表构造 ChatMessage 列表。"""
        return [ChatMessage(role=d["role"], content=d["content"]) for d in dicts]

    @staticmethod
    def FromChatMessages(messages: list[ChatMessage]) -> list[ChatMessage]:
        """原样返回 ChatMessage 列表（浅拷贝）。"""
        return list(messages)

    # ---- 四维调用 ----

    def Invoke(self, messages: list[ChatMessage]) -> ChatResponse:
        """同步非流式调用。"""
        return self._llm.Invoke(
            messages,
            requestParams=self._requestParams,
        )

    def Stream(self, messages: list[ChatMessage]) -> Iterator[ChatChunk]:
        """同步流式调用。"""
        return self._llm.Stream(
            messages,
            requestParams=self._requestParams,
        )

    async def InvokeAsync(
        self,
        messages: list[ChatMessage],
        cancellationToken: Optional[CancellationToken] = None,
    ) -> ChatResponse:
        """异步非流式调用，支持通过 CancellationToken 取消。"""
        return await self._llm.InvokeAsync(
            messages,
            cancellationToken=cancellationToken,
            requestParams=self._requestParams,
        )

    async def StreamAsync(
        self,
        messages: list[ChatMessage],
        cancellationToken: Optional[CancellationToken] = None,
    ) -> AsyncIterator[ChatChunk]:
        """异步流式调用，支持通过 CancellationToken 在 chunk 间取消。"""
        async for chunk in self._llm.StreamAsync(
            messages,
            cancellationToken=cancellationToken,
            requestParams=self._requestParams,
        ):
            yield chunk
