"""全局常量定义，项目内所有模块统一引用。"""

from enum import StrEnum


class ERoad(StrEnum):
    """项目关键路径枚举，成员值可通过 / 操作符拼接子路径。"""

    WORKSPACE = "workspace"
    
    MODELS_JSON = "workspace/models.json"
    MEMORY_DIR = "workspace/memory/"
    SKILLS_DIR = ".qoder/skills"
    RULES_DIR = ".qoder/rules"
    MCP_JSON_PATH = ".mcp.json"


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
