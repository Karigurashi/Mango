"""工作流节点流式事件类型枚举。"""

from enum import IntEnum


class EStreamEventType(IntEnum):
    """节点流式事件类型。

    Attributes:
        THINKING: 思考链增量内容。
        CONTENT: 正文增量内容。
        USAGE: Token 用量统计。
        DONE: 流结束通知。
    """

    THINKING = 0
    CONTENT = 1
    USAGE = 2
    DONE = 3
