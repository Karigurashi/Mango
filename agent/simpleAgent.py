"""SimpleAgent —— 纯对话 Agent，无 harness，不 ReAct 循环。

继承 BaseAgent，跳过所有 harness 功能（rules、skills、MCP、context compaction），
仅保留 BaseAgent 四维调用接口。事件通过 EventBusComponent 推送。

流式事件推送与缓冲区管理已下沉至 LLMComponent.StreamAsync，
SimpleAgent 仅负责状态编排（THINKING → FINISHED / ERROR）。
"""

from __future__ import annotations

from typing import Optional

from common.cancellationToken import CancellationToken
from llm.baseLLM import BaseLLM
from llm.provider.chatMessage import ChatMessage

from .component.eventBus.agentStreamEvent import AgentStreamEvent
from .component.eventBus.eventBusComponent import EventBusComponent
from .component.data.dataComponent import DataComponent
from .component.data.eAgentState import EAgentState
from .component.llm.llmComponent import LLMComponent
from .core.baseAgent import BaseAgent


class SimpleAgent(BaseAgent):
    """纯对话 Agent，无任何 harness 功能。

    继承 BaseAgent 四维调用接口，但跳过 LOD0 装填、
    ReAct 循环、工具调度和上下文压缩。适用于纯 LLM 对话场景。
    事件通过 EventBusComponent 推送，调用方订阅 EventBusComponent.Subscribe 即可接收。

    Usage::

        from llm import LLMManager
        from agent import SimpleAgent
        from agent.component.eventBus.agentStreamEvent import EAgentStreamEventType

        llm = LLMManager.GetProvider("gpt-4")
        agent = SimpleAgent(llm)

        async def onEvent(event):
            if event.eventType == EAgentStreamEventType.TEXT_DELTA:
                print(event.content, end="", flush=True)

        agent.GetComponent(EventBusComponent).Subscribe(onEvent)
        await agent.RunStreamAsync("Hello")
    """

    def __init__(self, llm: BaseLLM) -> None:
        super().__init__()

        self._dataComp = self.AddComponent(DataComponent)
        self._dataComp.llm = llm
        self._llmComp = self.GetComponent(LLMComponent)
        self._eventBusComp = self.GetComponent(EventBusComponent)

    # ---- 单轮纯对话 ----

    async def RunStreamAsync(
        self,
        userMessage: str,
        cancellationToken: Optional[CancellationToken] = None,
        systemPrompt: str = "",
    ) -> None:
        """流式单轮纯对话，事件通过 EventBusComponent 推送。

        LLMComponent.StreamAsync 内部管理缓冲区并推送
        ThinkingDelta / TextDelta / ThinkingComplete / TextComplete 事件，
        SimpleAgent 仅负责外围状态编排。

        Args:
            userMessage: 用户消息。
            cancellationToken: 取消令牌（可选）。
            systemPrompt: 系统提示词（可选），作为 SYSTEM 角色消息置于用户消息前。
        """
        self._EmitStateChange(EAgentState.THINKING)
        messages = []
        if systemPrompt:
            messages.append(ChatMessage.System(systemPrompt))
        messages.append(ChatMessage.User(userMessage))

        try:
            await self._llmComp.StreamAsync(
                messages, cancellationToken=cancellationToken,
            )
        except Exception as exc:
            self._EmitEvent(AgentStreamEvent.ErrorEvent(f"LLM call failed: {exc}"))
            self._EmitStateChange(EAgentState.ERROR)
            return

        self._EmitStateChange(EAgentState.FINISHED)
        self._EmitDone()

    # ---- 事件推送 helper ----

    def _EmitEvent(self, event: AgentStreamEvent) -> None:
        self._eventBusComp.Push(event)

    def _EmitStateChange(self, state: EAgentState, turnIndex: int = 0) -> None:
        self._dataComp.state = state
        self._EmitEvent(AgentStreamEvent.StateChange(state, turnIndex))

    def _EmitDone(self) -> None:
        self._EmitEvent(AgentStreamEvent.Done())
