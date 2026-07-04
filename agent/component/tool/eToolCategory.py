"""工具分类枚举。"""

from enum import IntEnum


class EToolCategory(IntEnum):
    """工具分类 —— 对应 Agent 可用的工具类型。

    Attributes:
        FILE: 文件操作（读写、搜索）。
        SHELL: Shell 命令执行。
        NETWORK: 网络请求。
        KNOWLEDGE: 知识检索（RAG、Memory）。
        AGENT: Agent 间通信（SubAgent、Task）。
        MCP: MCP 协议工具（由 MCP Server 提供）。
        CUSTOM: 用户自定义扩展工具。
    """

    FILE = 0
    SHELL = 1
    NETWORK = 2
    KNOWLEDGE = 3
    AGENT = 4
    WORKFLOW = 5
    MCP = 6
    CUSTOM = 7
