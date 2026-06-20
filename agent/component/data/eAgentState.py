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


# ---- 合法状态转移表 ----
#
# key 为当前状态，value 为允许转移的目标状态集合。
# 设计原则：
#   - IDLE 是入口，可进入 THINKING 或直接 ERROR；
#   - THINKING 是核心枢纽，可流向 ACTING/FINISHED/ERROR/WAITING_USER；
#   - ACTING 完成后回到 THINKING，或异常 ERROR/直接 FINISHED；
#   - 终态（FINISHED/ERROR）允许通过 IDLE 复位重新开始；
#   - 自转移（X -> X）默认禁止，避免冗余写入。

VALID_TRANSITIONS: dict[EAgentState, set[EAgentState]] = {
    EAgentState.IDLE: {EAgentState.THINKING, EAgentState.ERROR},
    EAgentState.THINKING: {
        EAgentState.ACTING,
        EAgentState.FINISHED,
        EAgentState.ERROR,
        EAgentState.WAITING_USER,
    },
    EAgentState.ACTING: {
        EAgentState.THINKING,
        EAgentState.FINISHED,
        EAgentState.ERROR,
    },
    EAgentState.WAITING_USER: {
        EAgentState.THINKING,
        EAgentState.IDLE,
        EAgentState.ERROR,
    },
    EAgentState.FINISHED: {EAgentState.IDLE, EAgentState.THINKING},
    EAgentState.ERROR: {EAgentState.IDLE, EAgentState.THINKING},
}
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
