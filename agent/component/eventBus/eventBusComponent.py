"""EventBusComponent —— Agent 流式事件总线组件，供外部监听器实时订阅。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from common.syncEventBus import SyncEventBus
from .agentStreamEvent import AgentStreamEvent
from agent.core.baseComponent import IComponent

if TYPE_CHECKING:
    from agent.core.baseAgent import BaseAgent


class EventBusComponent(SyncEventBus[AgentStreamEvent], IComponent):
    """Agent 流式事件总线组件。

    继承 SyncEventBus 泛型基类（绑定 AgentStreamEvent），
    同时实现 IComponent 生命周期接口。
    """

    def OnInitialize(self, agent: BaseAgent) -> None:
        """挂载后初始化。当前无需注入其他组件。"""
        pass

    def OnDestroy(self) -> None:
        """卸载时清空所有监听器，避免泄漏。"""
        self.RemoveAllListeners()
