"""ETaskProgressKind —— Workflow 进度/流式事件种类。"""

from enum import IntEnum


class ETaskProgressKind(IntEnum):
    """Workflow PROGRESS 事件的细分种类。"""

    FLOW_START = 0
    FLOW_DONE = 1
    FLOW_CANCEL = 2
    NODE_STATUS = 3
    AI_CONTENT = 4

