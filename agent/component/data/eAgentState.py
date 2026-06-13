"""Agent 状态机枚举 —— 控制 Agent 运行时的状态迁移。"""

from enum import IntEnum


class EAgentState(IntEnum):
    """Agent 运行时状态。

    Attributes:
        IDLE: 初始/等待用户输入。
        THINKING: LLM 推理中。
        ACTING: 工具执行中。
        WAITING_USER: 需要用户确认/输入。
        FINISHED: 本轮正常结束。
        ERROR: 异常终止。
    """

    IDLE = 0
    THINKING = 1
    ACTING = 2
    WAITING_USER = 3  # 预留：用户确认/输入中断（当前版本未启用）
    FINISHED = 4
    ERROR = 5
