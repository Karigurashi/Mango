"""工具抽象基类 —— 所有工具必须继承此基类。

对标 Claude Code Tool 体系 + LangChain BaseTool：
- 静态声明 name / description / parameters（LLM function calling 规格）。
- _invoke() 同步执行逻辑（子类覆盖）。
- _ainvoke() 异步执行逻辑（可选覆盖，默认回退 _invoke）。
- ExecuteAsync() 公共异步入口，统一对外接口。
"""

from __future__ import annotations

from abc import ABC
from typing import Any

from llm.provider.chatMessage import ToolSpec

from .eToolCategory import EToolCategory
from .toolResult import ToolResult


class AbstractTool(ABC):
    """工具抽象基类 —— 子类覆盖类属性声明元数据，实现 _invoke / _ainvoke 定义行为。

    执行模式（双轨制）::

        _invoke(**kwargs)   → 同步主逻辑（纯同步操作如文件读写实现此方法）
        _ainvoke(**kwargs)  → 异步逻辑（默认回退到 _invoke，异步操作如 subprocess 覆盖此方法）
        ExecuteAsync(**kwargs) → 公共异步入口，始终可用

    子类必须覆盖:
        - ``name``: 工具名称（LLM function name）。
        - ``description``: 工具描述。
        - ``parameters``: JSON Schema 参数定义。
        - ``category``: 工具分类枚举。
        - ``_invoke()``: 同步执行逻辑（返回 ToolResult）。

    Example::

        @G_ToolRegistry.Register
        class ReadFileTool(AbstractTool):
            name = "read_file"
            description = "Read the contents of a file"
            category = EToolCategory.FILE
            parameters = {
                "type": "object",
                "properties": {
                    "filePath": {"type": "string", "description": "..."},
                },
                "required": ["filePath"],
            }

            def _invoke(self, filePath: str) -> ToolResult:
                with open(filePath, "r") as f:
                    content = f.read()
                return ToolResult.Ok(content, toolName=self.name)
    """

    # ---- 子类覆盖: 元数据 ----

    name: str = ""
    """工具名称，作为 LLM function name。"""

    description: str = ""
    """工具描述，LLM 据此判断调用时机。"""

    category: EToolCategory = EToolCategory.CUSTOM
    """工具所属分类。"""

    parameters: dict[str, Any] = {}
    """JSON Schema 格式的参数定义。"""

    # ---- 子类覆盖: 执行逻辑 ----

    def _invoke(self, **kwargs) -> ToolResult:
        """同步执行逻辑 —— 子类覆盖此方法实现纯同步操作。

        文件读写、内存计算等操作仅需实现此方法。
        返回值自动被 _ainvoke 在线程池中异步包装。

        Args:
            **kwargs: 与 parameters 定义对应的关键字参数。

        Returns:
            ToolResult: 统一执行结果。

        Raises:
            NotImplementedError: 子类未实现 _invoke 或 _ainvoke。
        """
        raise NotImplementedError(
            f"{self.__class__.__name__}: must implement _invoke() or _ainvoke()"
        )

    async def _ainvoke(self, **kwargs) -> ToolResult:
        """异步执行逻辑 —— 默认回退到 _invoke。

        异步操作（subprocess、网络请求等）覆盖此方法避免阻塞事件循环。
        默认实现在线程池中执行 _invoke，保证 ExecuteAsync 始终异步兼容。

        Args:
            **kwargs: 与 parameters 定义对应的关键字参数。

        Returns:
            ToolResult: 统一执行结果。
        """
        import asyncio
        return await asyncio.to_thread(self._invoke, **kwargs)

    async def ExecuteAsync(self, **kwargs) -> ToolResult:
        """公共异步执行入口 —— 优先 _ainvoke，回退 _invoke。

        外部只需调用此方法，无需关心底层是同步还是异步实现。

        Args:
            **kwargs: 与 parameters 定义对应的关键字参数。

        Returns:
            ToolResult: 统一执行结果。
        """
        return await self._ainvoke(**kwargs)

    # ---- LLM 工具描述转换 ----

    def ToToolSpec(self) -> ToolSpec:
        """转换为 LLM 统一工具描述（ToolSpec）。

        Returns:
            ToolSpec 对象，可直接传给 LLMClient.BindTools()。
        """
        return ToolSpec(
            name=self.name,
            description=self.description,
            parameters=self.parameters,
        )

    @classmethod
    def GetToolInfo(cls) -> dict[str, Any]:
        """返回工具元数据，供外部检索和可视化。"""
        return {
            "name": cls.name,
            "description": cls.description,
            "category": cls.category.value,
            "parameters": cls.parameters,
        }

    # ---- 魔法方法 ----

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r}, category={self.category.value})"
