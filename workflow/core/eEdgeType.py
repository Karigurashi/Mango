"""工作流边类型枚举。"""

from enum import IntEnum


class EEdgeType(IntEnum):
    """边类型：OUT（常规流程边，0）、SUB_NODE（父节点到子节点的边，1）。"""

    OUT = 0
    SUB_NODE = 1
