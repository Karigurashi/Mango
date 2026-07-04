"""工作流节点分类枚举。"""

from enum import Enum


class ENodeCategory(Enum):
    """节点二分类：Action（行为）、Composite（组合）。"""

    ACTION = "Action"
    COMPOSITE = "Composite"
