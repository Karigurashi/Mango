"""全局常量定义，项目内所有模块统一引用。"""

from enum import StrEnum


class ERoad(StrEnum):
    WORKSPACE = "workspace"
    WORKSPACE_MODELS_JSON = "worksapce/models.json"


class ERole(StrEnum):
    """LLM 消息角色枚举，可替代字符串直接使用。

    Attributes:
        SYSTEM: 系统指令。
        USER: 用户输入。
        ASSISTANT: 模型回复。
        TOOL: 工具执行结果。
    """

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
