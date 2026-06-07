"""WorkflowGraph —— 图容器，管理 BaseNode 实例、边和节点位置。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .workflowEdge import WorkflowEdge
from .eEdgeType import EEdgeType
from .eNodeCategory import ENodeCategory
from .nodeRegistry import NodeRegistry

if TYPE_CHECKING:
    from .baseNode import BaseNode


class WorkflowGraph:
    """图的定义 —— 持有 BaseNode 实例、边列表及可视化坐标。

    图不持有运行时状态；执行时由 WorkflowExecutor 搭配 WorkflowContext 遍历。
    Node ID 统一为 int：正 ID 来自 JSON 前端配置，负 ID 来自程序化 AddNodeAuto。

    所有节点/边管理方法支持链式调用，返回 self。
    """

    def __init__(self) -> None:
        self._nodes: dict[int, "BaseNode"] = {}
        self._edges: list[WorkflowEdge] = []
        self._nodePositions: dict[int, dict[str, float]] = {}
        self._autoIdCounter: int = -1

    # ---- 自动 ID 节点添加（程序化使用，负 ID 区别于 JSON 端配置） ----

    def AddNodeAuto(
        self,
        executor: "BaseNode",
        x: float = 0,
        y: float = 0,
    ) -> int:
        """添加节点，自动分配负 ID（从 -1 递减），返回生成的 int ID。

        用于程序化动态创建节点，与 JSON 端配置的正 ID（1, 2, 3...）区分。
        注意：此方法返回 nodeId 而非 self，因为调用方需要拿到生成的 ID。
        """
        nodeId = self._autoIdCounter
        self._autoIdCounter -= 1
        self._nodes[nodeId] = executor
        self._nodePositions[nodeId] = {"x": x, "y": y}
        return nodeId

    # ---- 节点管理 ----

    def AddNode(
        self,
        nodeId: int,
        executor: "BaseNode",
        x: float = 0,
        y: float = 0,
    ) -> "WorkflowGraph":
        """添加 BaseNode 实例到图中（需显式指定 int ID）。"""
        self._nodes[nodeId] = executor
        self._nodePositions[nodeId] = {"x": x, "y": y}
        return self

    def RemoveNode(self, nodeId: int) -> "WorkflowGraph":
        """移除节点及其关联的所有边。"""
        self._nodes.pop(nodeId, None)
        self._nodePositions.pop(nodeId, None)
        self._edges = [
            e for e in self._edges
            if e.fromNodeId != nodeId and e.toNodeId != nodeId
        ]
        return self

    def HasNode(self, nodeId: int) -> bool:
        """检查节点是否存在。"""
        return nodeId in self._nodes

    def GetNode(self, nodeId: int) -> "BaseNode | None":
        """获取 BaseNode 实例。"""
        return self._nodes.get(nodeId)

    def GetNodeType(self, nodeId: int) -> str | None:
        """获取节点的类型字符串。"""
        node = self._nodes.get(nodeId)
        return node.nodeType if node else None

    def GetAllNodeIds(self) -> list[int]:
        """获取所有节点 ID。"""
        return list(self._nodes.keys())

    @property
    def NodeCount(self) -> int:
        """图中节点数量。"""
        return len(self._nodes)

    # ---- 边管理 ----

    def AddEdge(
        self,
        fromNodeId: int,
        toNodeId: int,
        edgeType: int = EEdgeType.OUT,
    ) -> "WorkflowGraph":
        """添加一条边（按节点 ID）。

        Args:
            fromNodeId: 源节点 ID。
            toNodeId: 目标节点 ID。
            edgeType: 边类型 int 值，默认 OUT(0)。
        """
        self._edges.append(WorkflowEdge(fromNodeId, toNodeId, edgeType))
        return self

    def AddEdgeObj(self, edge: WorkflowEdge) -> "WorkflowGraph":
        """添加一条边（传入 WorkflowEdge 对象）。"""
        self._edges.append(edge)
        return self

    def RemoveEdge(self, edge: WorkflowEdge) -> "WorkflowGraph":
        """移除指定边。"""
        self._edges = [e for e in self._edges if e != edge]
        return self

    def GetEdgesFrom(self, nodeId: int) -> list[WorkflowEdge]:
        """获取从指定节点出发的所有边。"""
        return [e for e in self._edges if e.fromNodeId == nodeId]

    def GetOutEdgesFrom(self, nodeId: int) -> list[WorkflowEdge]:
        """获取从指定节点出发的 OUT 类型边（常规流程边）。"""
        return [e for e in self._edges if e.fromNodeId == nodeId and e.edgeType == EEdgeType.OUT]

    def GetSubNodeEdgesFrom(self, nodeId: int) -> list[WorkflowEdge]:
        """获取从指定节点出发的 SUB_NODE 类型边（父节点到子节点边）。"""
        return [e for e in self._edges if e.fromNodeId == nodeId and e.edgeType == EEdgeType.SUB_NODE]

    def GetEdgesTo(self, nodeId: int) -> list[WorkflowEdge]:
        """获取指向指定节点的所有边。"""
        return [e for e in self._edges if e.toNodeId == nodeId]

    def GetAllEdges(self) -> list[WorkflowEdge]:
        """获取所有边。"""
        return list(self._edges)

    @property
    def EdgeCount(self) -> int:
        """边数量。"""
        return len(self._edges)

    # ---- 入口节点 ----

    def GetEntryNodes(self) -> list[int]:
        """查找所有无入边的 Action 类型节点（工作流入门）。"""
        entryNodes: list[int] = []
        allTargets = {e.toNodeId for e in self._edges}
        for nid, node in self._nodes.items():
            if node.category != ENodeCategory.ACTION:
                continue
            if nid not in allTargets:
                entryNodes.append(nid)
        return entryNodes

    # ---- 序列化 ----

    def ToDict(self) -> dict:
        """导出为可序列化的字典。节点 ID 为 int，name 随实例属性序列化。"""
        nodesData: list[dict] = []
        for nid, node in self._nodes.items():
            nodeDict: dict = {
                "id": nid,
                "type": node.nodeType,
                "x": self._nodePositions.get(nid, {}).get("x", 0),
                "y": self._nodePositions.get(nid, {}).get("y", 0),
            }
            # 用户自定义 name（仅非 None 时导出）
            if node.name is not None:
                nodeDict["name"] = node.name
            # 可配置参数（排除元数据和 name）
            config = {
                k: v for k, v in vars(node).items()
                if not k.startswith("_") and k not in (
                    "nodeType", "category", "displayName", "description", "name"
                )
            } or None
            if config:
                nodeDict["config"] = config
            nodesData.append(nodeDict)

        return {
            "nodes": nodesData,
            "edges": [e.ToDict() for e in self._edges],
        }

    @staticmethod
    def FromDict(data: dict) -> "WorkflowGraph":
        """从字典反序列化。节点 ID 解析为 int。"""
        graph = WorkflowGraph()
        for nodeData in data.get("nodes", []):
            nodeClass = NodeRegistry.Get(nodeData["type"])
            if nodeClass is None:
                raise ValueError(f"Unknown node type '{nodeData['type']}'")
            config = dict(nodeData.get("config") or {})
            # 从顶层提取 name 字段
            if "name" in nodeData and nodeData["name"] is not None:
                config["name"] = nodeData["name"]
            instance = nodeClass(**config)
            graph.AddNode(
                nodeId=int(nodeData["id"]),
                executor=instance,
                x=float(nodeData.get("x", 0)),
                y=float(nodeData.get("y", 0)),
            )
        for edgeData in data.get("edges", []):
            graph.AddEdgeObj(WorkflowEdge.FromDict(edgeData))
        return graph

    def __repr__(self) -> str:
        return f"WorkflowGraph(nodes={len(self._nodes)}, edges={len(self._edges)})"
