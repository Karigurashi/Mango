"""工作流流式事件类型枚举与事件数据类。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from .eExecutionStatus import EExecutionStatus


class EStreamEventType(IntEnum):
    """节点流式事件类型。

    Attributes:
        AI_THINKING: 思考链增量内容。
        AI_CONTENT: 正文增量内容。
        FLOW_START: 流开始通知。
        FLOW_DONE: 流结束通知。
        NODE_STATUS: 节点执行状态变更。
    """

    AI_THINKING = 0
    AI_CONTENT = 1
    FLOW_START = 2
    FLOW_DONE = 3
    NODE_STATUS = 4


@dataclass(slots=True)
class WorkflowStreamEvent:
    """工作流流式事件，供 WorkflowEventBus 同步推送。

    Attributes:
        workflowId: 所属工作流 ID。
        nodeId: 发起事件的节点 ID。
        agentId: 发起事件的 Agent 实例标识，0 表示非 Agent 节点。
        eventType: 事件类型。
        status: 节点执行状态，NODE_STATUS 事件使用。
        message: AI_CONTENT / AI_THINKING / FLOW_DONE。
    """

    workflowId: int
    nodeId: int
    agentId: int
    eventType: EStreamEventType
    status: EExecutionStatus | None = None
    message: str = ""
