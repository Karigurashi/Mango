"""全局工具注册表 —— 管理所有 Agent 工具，支持装饰器注册和外部扩展。

对标 Claude Code Tool 调度机制：
- 装饰器注册：@G_ToolRegistry.Register 自动注册工具类。
- 外部注册：RegisterTool() 接受已实例化的工具对象。
- ToolSpec 导出：GetAllToolSpecs() 直接给 LLMClient.BindTools() 使用。
- 调度分发：DispatchAsync() 根据 LLM ToolCall 查找工具并异步执行。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from llm.provider.chatMessage import ToolSpec, ToolCall

from .eToolCategory import EToolCategory
from .toolResult import ToolResult

if TYPE_CHECKING:
    from .abstractTool import AbstractTool


class ToolRegistry:
    """全局单例注册表，按名称索引所有工具。

    用法::

        from agent.tool.toolRegistry import G_ToolRegistry

        # 方式一：装饰器注册（推荐）
        @G_ToolRegistry.Register
        class ReadFileTool(AbstractTool):
            name = "read_file"
            ...

        # 方式二：外部实例注册
        G_ToolRegistry.RegisterTool(myCustomTool)

        # 绑定到 LLM
        specs = G_ToolRegistry.GetAllToolSpecs()
        llmClient.BindTools(specs)

        # 分发 LLM ToolCall
        result = await G_ToolRegistry.DispatchAsync(toolCall)
    """

    _instance: ToolRegistry | None = None

    def __new__(cls) -> ToolRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tools: dict[str, "AbstractTool"] = {}
            cls._instance._toolClasses: dict[str, type["AbstractTool"]] = {}
        return cls._instance

    # ---- 装饰器注册 ----

    def Register(self, toolClass: type["AbstractTool"]) -> type["AbstractTool"]:
        """装饰器：将工具类注册到全局表。

        工具类必须声明 ``name`` 类属性。

        Returns:
            原样返回工具类，不改变其行为。
        """
        toolName = getattr(toolClass, "name", "")
        if not toolName:
            raise ValueError(f"{toolClass.__name__} must define a non-empty 'name' class attribute")
        self._toolClasses[toolName] = toolClass
        return toolClass

    # ---- 外部实例注册 ----

    def RegisterTool(self, tool: "AbstractTool") -> None:
        """注册已实例化的工具对象（用于外部扩展）。

        Args:
            tool: 已实例化的 AbstractTool 子类对象。
        """
        if not tool.name:
            raise ValueError("Tool must have a non-empty name")
        self._tools[tool.name] = tool

    def RegisterTools(self, tools: list["AbstractTool"]) -> None:
        """批量注册工具实例。"""
        for tool in tools:
            self.RegisterTool(tool)

    # ---- 注销 ----

    def Unregister(self, name: str) -> None:
        """移除指定工具（同时移除类和实例注册）。"""
        self._tools.pop(name, None)
        self._toolClasses.pop(name, None)

    # ---- 查询 ----

    def Get(self, name: str) -> "AbstractTool | None":
        """按名称获取工具实例。

        优先返回已实例化的工具，其次从注册类创建临时实例。
        """
        if name in self._tools:
            return self._tools[name]

        toolClass = self._toolClasses.get(name)
        if toolClass is not None:
            return toolClass()

        return None

    def GetClass(self, name: str) -> type["AbstractTool"] | None:
        """按名称获取工具类。"""
        return self._toolClasses.get(name)

    def GetAll(self) -> dict[str, "AbstractTool"]:
        """获取所有工具实例（类注册的即时实例化）。"""
        result: dict[str, "AbstractTool"] = {}
        for name, toolClass in self._toolClasses.items():
            if name not in self._tools:
                result[name] = toolClass()
            else:
                result[name] = self._tools[name]
        for name, tool in self._tools.items():
            if name not in result:
                result[name] = tool
        return result

    def GetByCategory(self, category: EToolCategory) -> list["AbstractTool"]:
        """按分类获取工具实例。"""
        result: list["AbstractTool"] = []
        for tool in self.GetAll().values():
            if tool.category == category:
                result.append(tool)
        return result

    def GetByCategories(self, categories: list[EToolCategory]) -> list["AbstractTool"]:
        """按多个分类获取工具实例。"""
        result: list["AbstractTool"] = []
        catSet = set(categories)
        for tool in self.GetAll().values():
            if tool.category in catSet:
                result.append(tool)
        return result

    # ---- ToolSpec 导出 ----

    def GetAllToolSpecs(self) -> list[ToolSpec]:
        """获取所有工具的 ToolSpec 列表，可直接传给 LLMClient.BindTools()。

        Returns:
            ToolSpec 列表，可用于 LLM function calling 绑定。
        """
        return [tool.ToToolSpec() for tool in self.GetAll().values()]

    def GetToolSpecsByCategory(self, category: EToolCategory) -> list[ToolSpec]:
        """按分类获取 ToolSpec。"""
        return [tool.ToToolSpec() for tool in self.GetByCategory(category)]

    # ---- 调度分发 ----

    async def DispatchAsync(self, toolCall: ToolCall) -> ToolResult:
        """根据 LLM ToolCall 查找工具并异步执行。

        这是连接 LLM function calling 与工具实际执行的桥梁。

        Args:
            toolCall: LLM 返回的 ToolCall（含 name, arguments, id）。

        Returns:
            ToolResult: 工具执行结果，可直接注入 LLM context。
        """
        tool = self.Get(toolCall.name)
        if tool is None:
            return ToolResult.Fail(
                f"Unknown tool '{toolCall.name}'. Available: {', '.join(sorted(self._allToolNames()))}",
                toolName=toolCall.name,
            )

        try:
            result = await tool.ExecuteAsync(**toolCall.arguments)
            return result.WithToolName(toolCall.name)
        except Exception as exc:
            return ToolResult.Fail(
                f"Tool '{toolCall.name}' execution failed: {str(exc)}",
                toolName=toolCall.name,
            )

    async def DispatchBatchAsync(self, toolCalls: list[ToolCall]) -> list[ToolResult]:
        """批量并发分发多个工具调用。

        Args:
            toolCalls: LLM 返回的多个 ToolCall。

        Returns:
            与输入顺序对应的 ToolResult 列表。
        """
        import asyncio
        tasks = [self.DispatchAsync(tc) for tc in toolCalls]
        return list(await asyncio.gather(*tasks))

    # ---- 元数据 ----

    def GetAllToolInfo(self) -> list[dict]:
        """返回所有工具元数据，供可视化/调试。"""
        return [tool.GetToolInfo() for tool in self.GetAll().values()]

    # ---- 管理 ----

    def Count(self) -> int:
        """已注册工具总数（类注册 + 实例注册去重）。"""
        return len(self.GetAll())

    def Clear(self) -> None:
        """清空所有注册（谨慎使用）。"""
        self._tools.clear()
        self._toolClasses.clear()

    def LoadBuiltins(self) -> int:
        """加载所有内置工具。

        按分类从子目录加载，使用 importlib.reload 确保 Clear() 后能重新注册。

        Returns:
            加载的工具数量。
        """
        import importlib
        from . import builtin as _builtin

        # file/
        importlib.reload(_builtin.file.readFileTool)
        importlib.reload(_builtin.file.writeFileTool)
        importlib.reload(_builtin.file.deleteFileTool)
        importlib.reload(_builtin.file.listDirTool)
        importlib.reload(_builtin.file.searchFileTool)
        importlib.reload(_builtin.file.grepCodeTool)
        # shell/
        importlib.reload(_builtin.shell.bashTool)
        # network/
        importlib.reload(_builtin.network.fetchContentTool)
        importlib.reload(_builtin.network.searchWebTool)

        return self.Count()

    # ---- 内部 ----

    def _allToolNames(self) -> list[str]:
        """返回所有已注册工具名称（用于错误提示）。"""
        return list(self._toolClasses.keys()) + [
            name for name in self._tools if name not in self._toolClasses
        ]

    # ---- 魔法方法 ----

    def __repr__(self) -> str:
        return f"ToolRegistry(tools={self.Count()})"

    def __contains__(self, name: str) -> bool:
        return name in self._tools or name in self._toolClasses


# ---- 全局单例 ----

G_ToolRegistry = ToolRegistry()
"""全局工具注册表单例，框架唯一入口。"""
