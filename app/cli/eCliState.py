"""CLI 状态机枚举 —— 控制 CLI REPL 生命周期状态迁移。"""

from enum import IntEnum


class ECliState(IntEnum):
    """CLI 运行时状态。

    Attributes:
        IDLE: 等待用户输入。
        RUNNING: Agent 执行中，Ctrl+C 触发取消。
        CANCELLING: 取消信号已发出，等待 Agent 优雅停止。
        EXITING: 应用关闭中。
    """

    IDLE = 0
    RUNNING = 1
    CANCELLING = 2
    EXITING = 3
