"""工作流节点分类枚举。"""

from enum import Enum


class ENodeCategory(Enum):
    """节点三分类：Action（行为）、Condition（条件）、Composite（组合）。"""

    ACTION = "Action"
    CONDITION = "Condition"
    COMPOSITE = "Composite"
