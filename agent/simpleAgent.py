"""SimpleAgent —— 纯对话 Agent，无 harness，不 ReAct 循环。

继承 BaseAgent，跳过所有 harness 功能（rules、skills、MCP、context compaction），
仅保留 BaseAgent 四维调用接口。RunAsync 为单轮纯对话。
"""

from __future__ import annotations

from typing import AsyncIterator, Optional

from common.cancellationToken import CancellationToken
from llm.baseLLM import BaseLLM
from llm.provider.chatMessage import ChatMessage

from .agentStreamEvent import AgentStreamEvent, EAgentStreamEventType
from .core.baseAgent import BaseAgent
from .component.data.dataComponent import DataComponent
from .component.llm.llmComponent import LLMComponent


class SimpleAgent(BaseAgent):
    """纯对话 Agent，无任何 harness 功能。

    继承 BaseAgent 四维调用接口，但跳过 LOD0 装填、
    ReAct 循环、工具调度和上下文压缩。适用于纯 LLM 对话场景。

    Usage::

        from llm import LLMManager
        from agent import SimpleAgent

        llm = LLMManager.GetProvider("gpt-4")
        agent = SimpleAgent(llm)
        async for event in agent.RunAsync("Hello"):
            if event.eventType == EAgentStreamEventType.TEXT_DELTA:
                print(event.content, end="", flush=True)
    """

    def __init__(self, llm: BaseLLM) -> None:
        super().__init__()
        self._dataComp = self.AddComponent(DataComponent)
        self._dataComp.llm = llm
        self._llmComp = self.AddComponent(LLMComponent)
        self._llmComp.llm = llm
        self.InitAllComponents()

    # ---- 单轮纯对话 ----

    async def RunAsync(
        self,
        userMessage: str,
        cancellationToken: Optional[CancellationToken] = None,
    ) -> AsyncIterator[AgentStreamEvent]:
        """单轮纯对话，不涉及 harness / ReAct / 工具。"""
        messages = [ChatMessage.User(userMessage)]
        fullContent = ""

        async for chunk in self._llmComp.StreamAsync(
            messages, cancellationToken=cancellationToken,
        ):
            if chunk.content:
                fullContent += chunk.content
                yield self._EmitEvent(AgentStreamEvent.TextDelta(chunk.content))

        yield self._EmitEvent(AgentStreamEvent.Done())
