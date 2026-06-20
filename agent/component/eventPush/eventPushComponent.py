"""EventPushComponent —— Agent 流式事件推送组件，供外部监听器实时订阅。
"""

from __future__ import annotations

from typing import Callable, TYPE_CHECKING

from agent.agentStreamEvent import AgentStreamEvent
from agent.core.baseComponent import IComponent
from common.logger import Logger

if TYPE_CHECKING:
    from agent.core.baseAgent import BaseAgent


class EventPushComponent(IComponent):
    """Agent 流式事件推送组件。

    - Subscribe(callback): 注册同步回调。
    - Push(event): 遍历所有回调并逐一调用。

    监听器异常被隔离，不会中断 Agent 主循环。
    """

    def __init__(self) -> None:
        self._listeners: list[Callable[[AgentStreamEvent], None]] = []

    def OnInitialize(self, agent: BaseAgent) -> None:
        """挂载后初始化。当前无需注入其他组件。"""
        pass

    def OnDestroy(self) -> None:
        """卸载时清空所有监听器，避免泄漏。"""
        self._listeners.clear()

    def Subscribe(self, callback: Callable[[AgentStreamEvent], None]) -> None:
        """注册事件监听器。callback 为同步函数。"""
        self._listeners.append(callback)

    def Unsubscribe(self, callback: Callable[[AgentStreamEvent], None]) -> None:
        """移除事件监听器。"""
        self._listeners.remove(callback)

    def Push(self, event: AgentStreamEvent) -> None:
        """推送事件给所有监听器。"""
        for listener in self._listeners:
            try:
                listener(event)
            except Exception as exc:
                Logger.Warning(f"EventPushComponent: listener failed: {exc}")
