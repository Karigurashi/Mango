"""Workflow 顶层类 —— 工作流定义，封装图结构、变量声明及 JSON 序列化。"""

from __future__ import annotations

import asyncio
import json
from enum import IntEnum
from typing import Any, Optional

from .core.workflowContext import WorkflowContext
from .core.workflowGraph import WorkflowGraph
from .core.workflowExecutor import WorkflowExecutor
from .core.nodeRegistry import NodeRegistry
from .core.workflowEdge import WorkflowEdge
from .core.workflowEventBus import WorkflowEventBus
from common.cancellationToken import CancellationToken


class EWorkflowStatus(IntEnum):
    """Workflow 全局运行时状态。

    Attributes:
        RUNNING: 正在执行中。
        COMPLETED: 执行成功完成。
        FAILED: 执行失败。
        CANCELLED: 被取消。
    """

    RUNNING = 0
    COMPLETED = 1
    FAILED = 2
    CANCELLED = 3


class Workflow:
    """工作流定义 —— 由名称和图结构组成。

    Attributes:
        id: 自增全局唯一标识。
        name: 工作流名称。
        status: 运行时状态（EWorkflowStatus 枚举）。
        graph: 图结构（BaseNode + Edge）。
    """

    _nextId: int = 0

    def __init__(self, name: str = "") -> None:
        self.id: int = Workflow._nextId
        Workflow._nextId += 1
        self.name = name
        self.status: EWorkflowStatus = EWorkflowStatus.RUNNING
        self.graph = WorkflowGraph()
        self.context = WorkflowContext()
        self.eventBus = WorkflowEventBus()

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
        for nodeData in jsonData.get("nodes", []):
            nodeClass = NodeRegistry.Get(nodeData["type"])
            if nodeClass is None:
                raise ValueError(f"Unknown node type '{nodeData['type']}'")
            config = dict(nodeData.get("config") or {})
            if "name" in nodeData and nodeData["name"] is not None:
                config["name"] = nodeData["name"]
            instance = nodeClass(**config)
            wf.graph.AddNode(
                nodeId=int(nodeData["id"]),
                executor=instance,
                x=float(nodeData.get("x", 0)),
                y=float(nodeData.get("y", 0)),
            )
        for edgeData in jsonData.get("edges", []):
            wf.graph.AddEdgeObj(WorkflowEdge.FromDict(edgeData))
        return wf

    def ToJson(self) -> dict:
        """导出为 JSON 字典。"""
        result: dict[str, Any] = {"name": self.name}
        nodesData: list[dict] = []
        for nid in self.graph.GetAllNodeIds():
            node = self.graph.GetNode(nid)
            if node is None:
                continue
            x, y = node.x, node.y
            nodeDict: dict = {"id": nid, "type": node.nodeType, "x": x, "y": y}
            if node.name is not None:
                nodeDict["name"] = node.name
            config = {
                k: v for k, v in vars(node).items()
                if not k.startswith("_") and k not in (
                    "nodeType", "category", "displayName", "description", "name", "x", "y"
                )
            } or None
            if config:
                nodeDict["config"] = config
            nodesData.append(nodeDict)
        result["nodes"] = nodesData
        result["edges"] = [e.ToDict() for e in self.graph.GetAllEdges()]
        return result

    def ToJsonString(self, indent: int = 2) -> str:
        """导出为格式化的 JSON 字符串。"""
        return json.dumps(self.ToJson(), indent=indent, ensure_ascii=False)

    # ---- 执行 ----

    async def ExecuteAsync(
        self, cancellationToken: Optional[CancellationToken] = None
    ) -> "WorkflowContext":
        """异步执行此工作流，执行过程中自动刷新 status。

        Args:
            cancellationToken: 取消令牌，支持协作式取消。未传则自动创建。

        Returns:
            执行后的 WorkflowContext，包含所有中间结果和输出。
        """
        if cancellationToken is None:
            cancellationToken = CancellationToken()
        try:
            result = await WorkflowExecutor.ExecuteAsync(
                self, self.context, self.eventBus, cancellationToken
            )
            self.status = EWorkflowStatus.COMPLETED
            return result
        except asyncio.CancelledError:
            self.status = EWorkflowStatus.CANCELLED
            raise
        except Exception:
            self.status = EWorkflowStatus.FAILED
            raise

    # ---- 魔法方法 ----

    def __repr__(self) -> str:
        return (
            f"Workflow(name={self.name!r}, "
            f"nodes={self.graph.NodeCount}, "
            f"edges={self.graph.EdgeCount})"
        )
