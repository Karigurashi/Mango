"""工作流节点执行状态枚举。"""

from enum import IntEnum


class EExecutionStatus(IntEnum):
    """节点执行状态。

    Attributes:
        RUNNING: 节点正在执行。
        COMPLETED: 节点执行完成。
        FAILED: 节点执行失败。
        CANCELLED: 节点被取消。
    """

    RUNNING = 0
    COMPLETED = 1
    FAILED = 2
    CANCELLED = 3
