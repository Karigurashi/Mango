"""Agent Tool —— Agent 工具调度与管理层。

对标 Claude Code Tool 体系 + LangChain BaseTool，提供：
    - AbstractTool: 工具抽象基类，声明 name/description/parameters + ExecuteAsync。
    - ToolResult: 统一执行结果封装。
    - EToolCategory: 工具分类枚举（File / Shell / Network / Knowledge / Agent / MCP / Custom）。
    - ToolRegistry: 全局注册表单例，支持装饰器注册、外部扩展、LLM 工具绑定、调度分发。
    - builtin: 内置基础工具（ReadFile / WriteFile / Bash）。

外部扩展方式::

    from agent.tool import AbstractTool, EToolCategory, G_ToolRegistry

    # 方式一：装饰器注册
    @G_ToolRegistry.Register
    class MyTool(AbstractTool):
        name = "my_tool"
        description = "My custom tool"
        category = EToolCategory.CUSTOM
        parameters = {...}

        async def ExecuteAsync(self, **kwargs) -> ToolResult:
            ...

    # 方式二：实例注册
    G_ToolRegistry.RegisterTool(myToolInstance)

    # 绑定到 LLM
    specs = G_ToolRegistry.GetAllToolSpecs()
    llmClient.BindTools(specs)

    # 分发 LLM ToolCall
    result = await G_ToolRegistry.DispatchAsync(toolCall)
"""

from .abstractTool import AbstractTool
from .eToolCategory import EToolCategory
from .toolRegistry import G_ToolRegistry, ToolRegistry
from .toolResult import ToolResult

__all__ = [
    "AbstractTool",
    "EToolCategory",
    "G_ToolRegistry",
    "ToolRegistry",
    "ToolResult",
]
