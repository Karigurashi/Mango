"""WorkflowEdge —— 节点间有向边，去除引脚概念，直接 node-to-node 连接。"""

from __future__ import annotations

from typing import Any

from .eEdgeType import EEdgeType


class WorkflowEdge:
    """节点间有向边，表达从源节点到目标节点的连接。

    与 MAF Edge 对齐：不再有引脚名，边直接连接两个 BaseNode。

    Attributes:
        fromNodeId: 源节点 ID（int）。
        toNodeId: 目标节点 ID（int）。
        edgeType: 边类型 int 值（0=OUT 常规流程边，1=SUB_NODE 父到子节点的边）。
    """

    def __init__(
        self,
        fromNodeId: int,
        toNodeId: int,
        edgeType: int = EEdgeType.OUT,
    ) -> None:
        self.fromNodeId: int = fromNodeId
        self.toNodeId: int = toNodeId
        self.edgeType: int = int(edgeType)

    # ---- 序列化 ----

    @staticmethod
    def FromDict(data: dict[str, Any]) -> "WorkflowEdge":
        """从字典反序列化。

        支持格式::

            {"from": 1, "to": 2}
            {"from": 1, "to": 2, "type": 1}
        """
        edgeType = data.get("type", EEdgeType.OUT)
        return WorkflowEdge(
            fromNodeId=int(data["from"]),
            toNodeId=int(data["to"]),
            edgeType=int(edgeType),
        )

    def ToDict(self) -> dict[str, Any]:
        """导出为字典。"""
        result: dict[str, Any] = {
            "from": self.fromNodeId,
            "to": self.toNodeId,
        }
        if self.edgeType != EEdgeType.OUT:
            result["type"] = self.edgeType
        return result

    # ---- 魔法方法 ----

    def __repr__(self) -> str:
        try:
            typeName = EEdgeType(self.edgeType).name
        except ValueError:
            typeName = f"TYPE({self.edgeType})"
        return f"{self.fromNodeId} --[{typeName}]--> {self.toNodeId}"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, WorkflowEdge):
            return False
        return (
            self.fromNodeId == other.fromNodeId
            and self.toNodeId == other.toNodeId
            and self.edgeType == other.edgeType
        )

    def __hash__(self) -> int:
        return hash((self.fromNodeId, self.toNodeId, self.edgeType))
