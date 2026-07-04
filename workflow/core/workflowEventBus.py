"""WorkflowEventBus —— 工作流同步事件总线，独立于 Agent 框架。"""

from __future__ import annotations

from common.syncEventBus import SyncEventBus
from .workflowStreamEvent import WorkflowStreamEvent


class WorkflowEventBus(SyncEventBus[WorkflowStreamEvent]):
    """工作流级同步事件总线。

    继承 SyncEventBus 泛型基类，绑定 WorkflowStreamEvent 事件类型。
    """
    pass
