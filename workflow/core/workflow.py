"""Workflow 顶层类 —— 工作流定义，封装图结构、变量声明及 JSON 序列化。"""

from __future__ import annotations

import json
from typing import Any, Optional, Awaitable, Callable, TYPE_CHECKING

from .workflowGraph import WorkflowGraph
from .workflowContext import NodeStreamCallback

if TYPE_CHECKING:
    from common.cancellationToken import CancellationToken

# 执行事件回调签名（与 WorkflowExecutor 保持一致）
NodeEventCallback = Callable[[int, str], Awaitable[None]]


class Workflow:
    """工作流定义 —— 由名称和图结构组成。

    Attributes:
        name: 工作流名称。
        graph: 图结构（BaseNode + Edge）。
    """

    def __init__(self, name: str = "") -> None:
        self.name = name
        self.graph = WorkflowGraph()

    # ---- JSON 序列化 ----

    @staticmethod
    def FromJson(jsonData: dict | str) -> "Workflow":
        """从 JSON 字典或字符串反序列化工作流。

        Args:
            jsonData: JSON 字典或 JSON 字符串。

        Example::

            wf = Workflow.FromJson('''
            {
                "name": "Test",
                "nodes": [
                    {"id": 1, "type": "Action/BeginPlay", "x": 0, "y": 0}
                ],
                "edges": [
                    {"from": 1, "to": 2}
                ]
            }
            ''')
        """
        if isinstance(jsonData, str):
            jsonData = json.loads(jsonData)

        wf = Workflow(name=jsonData.get("name", ""))
        wf.graph = WorkflowGraph.FromDict(jsonData)
        return wf

    def ToJson(self) -> dict:
        """导出为 JSON 字典。"""
        result: dict[str, Any] = {"name": self.name}
        result.update(self.graph.ToDict())
        return result

    def ToJsonString(self, indent: int = 2) -> str:
        """导出为格式化的 JSON 字符串。"""
        return json.dumps(self.ToJson(), indent=indent, ensure_ascii=False)

    # ---- 执行 ----

    async def ExecuteAsync(
        self,
        ctx: "WorkflowContext | None" = None,
        onNodeEvent: Optional[NodeEventCallback] = None,
        onNodeStream: Optional[NodeStreamCallback] = None,
        cancellationToken: Optional["CancellationToken"] = None,
    ) -> "WorkflowContext":
        """异步执行此工作流。

        Args:
            ctx: 外部上下文（可选），不传自动创建。
            onNodeEvent: 节点执行事件回调 async(nodeId, status)。
            onNodeStream: 节点流式输出回调 async(nodeId, eventType, data)。
            cancellationToken: 取消令牌（可选），支持协作式中断工作流及底层 LLM 调用。

        Returns:
            执行后的 WorkflowContext。
        """
        from .workflowExecutor import WorkflowExecutor
        from .workflowContext import WorkflowContext as _WorkflowContext
        return await WorkflowExecutor.ExecuteAsync(
            self, ctx, onNodeEvent=onNodeEvent, onNodeStream=onNodeStream, cancellationToken=cancellationToken
        )

    # ---- 魔法方法 ----

    def __repr__(self) -> str:
        return (
            f"Workflow(name={self.name!r}, "
            f"nodes={self.graph.NodeCount}, "
            f"edges={self.graph.EdgeCount})"
        )
