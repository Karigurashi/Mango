"""Workflow —— 工作流定义，继承 TaskT，封装图结构及运行时。"""

from __future__ import annotations

from typing import Callable, Optional

from common.syncEventBus import SyncEventBus
from task.core.task import TaskT
from .core.workflowContext import WorkflowContext
from .core.workflowGraph import WorkflowGraph
from .core.workflowExecutor import WorkflowExecutor
from .core.taskProgressData import TaskProgressData
from common.cancellationToken import CancellationToken


class Workflow(TaskT[dict[str, object]]):
    """工作流定义 —— 继承 TaskT，由名称和图结构组成。

    进度通过 Workflow 自身的 typed progress listener 推送，由 WorkflowComponent / 外部监听器消费。

    Attributes:
        graph: 图结构（BaseNode + Edge）。
        context: 运行时上下文。
    """

    def __init__(self, name: str = "") -> None:
        super().__init__(name=name)
        self.graph = WorkflowGraph()
        self.context = WorkflowContext()
        self.summary: dict[str, object] = {}
        self._progressBus: SyncEventBus[TaskProgressData] = SyncEventBus()

    def AddProgressListener(self, callback: Callable[[TaskProgressData], None]) -> None:
        """注册 Workflow 进度监听器。"""
        self._progressBus.AddListener(callback)

    def RemoveProgressListener(self, callback: Callable[[TaskProgressData], None]) -> None:
        """移除 Workflow 进度监听器。"""
        self._progressBus.RemoveListener(callback)

    def _PushProgress(self, data: TaskProgressData) -> None:
        self._progressBus.Push(data)

    async def ExecuteAsync(
        self,
        cancellationToken: Optional[CancellationToken] = None,
    ) -> dict[str, object]:
        """异步执行此工作流，并返回摘要。"""
        if cancellationToken is None:
            cancellationToken = CancellationToken()
        self.context = WorkflowContext()
        ctx = await WorkflowExecutor.ExecuteAsync(
            self,
            self.context,
            cancellationToken,
            progressSink=self._PushProgress,
        )
        self.summary = {
            "nodeCount": self.graph.NodeCount,
            "round": ctx.ExecutionRound,
            "status": "completed",
        }
        return self.summary

    def __repr__(self) -> str:
        return (
            f"Workflow(name={self.info.name!r}, "
            f"nodes={self.graph.NodeCount}, "
            f"edges={self.graph.EdgeCount})"
        )
