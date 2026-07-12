"""InjectionComponent —— 将后台产生的内容推送到 Agent 主循环，忙时排队。"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from agent.component.data.dataComponent import DataComponent
from agent.component.data.eAgentState import EAgentState
from agent.component.eventBus.agentStreamEvent import EAgentStreamEventType
from agent.core.baseComponent import IComponent

if TYPE_CHECKING:
    from agent.component.eventBus.agentStreamEvent import AgentStreamEvent
    from agent.core.baseAgent import BaseAgent


class InjectionComponent(IComponent):
    """后台内容注入组件 —— 在 Agent 空闲时将内容推入主循环。

    由 ScheduleComponent / WorkflowComponent 等后台任务消费者调用，
    统一处理"Agent 忙时排队 → DONE 事件后冲刷"的推送模式。
    """

    def OnInitialize(self, agent: BaseAgent) -> None:
        self._agent: BaseAgent = agent
        self._dataComp = agent.GetComponent(DataComponent)

        from agent.component.eventBus.eventBusComponent import EventBusComponent
        self._eventBus = agent.GetComponent(EventBusComponent)
        self._eventBus.AddListener(self._OnAgentEvent)

        self._pendingContents: list[str] = []

    def OnDestroy(self) -> None:
        self._eventBus.RemoveListener(self._OnAgentEvent)
        self._pendingContents.clear()

    def InjectAsync(self, content: str) -> None:
        """将内容推送到 Agent 主循环；若 Agent 忙碌则排队等待。

        Args:
            content: 待注入的文本内容。
        """
        if self._IsAgentBusy():
            self._pendingContents.append(content)
        else:
            self._DoInject(content)

    def _IsAgentBusy(self) -> bool:
        return self._dataComp.state in (
            EAgentState.THINKING,
            EAgentState.ACTING,
            EAgentState.WAITING_USER,
        )

    def _OnAgentEvent(self, event: AgentStreamEvent) -> None:
        if event.eventType == EAgentStreamEventType.DONE:
            pending = self._pendingContents[:]
            self._pendingContents.clear()
            for content in pending:
                self._DoInject(content)

    def _DoInject(self, content: str) -> None:
        asyncio.create_task(self._agent.RunStreamAsync(content))
