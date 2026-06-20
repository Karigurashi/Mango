"""工具抽象基类 —— 所有工具必须继承此基类。

对标 Claude Code Tool 体系 + LangChain BaseTool：
- 静态声明 name / description / parameters（LLM function calling 规格）。
- _Invoke() 同步执行逻辑（子类覆盖）。
- _InvokeAsync() 异步执行逻辑（可选覆盖，默认回退 _Invoke）。
- ExecuteAsync() 公共异步入口，统一对外接口。
"""

from __future__ import annotations

import os
from abc import ABC
from typing import Any

from llm.provider.chatMessage import ToolSpec

from agent.component.contex.eContextLodLevel import EContextLodLevel

from .eToolCategory import EToolCategory
from .toolResult import ToolResult


class BaseTool(ABC):
    """工具抽象基类 —— 子类覆盖类属性声明元数据，实现 _Invoke / _InvokeAsync 定义行为。

    执行模式（双轨制）::

        _Invoke(**kwargs)   → 同步主逻辑（纯同步操作如文件读写实现此方法）
        _InvokeAsync(**kwargs)  → 异步逻辑（默认回退到 _Invoke，异步操作如 subprocess 覆盖此方法）
        ExecuteAsync(**kwargs) → 公共异步入口，始终可用

    子类必须覆盖:
        - ``name``: 工具名称（LLM function name）。
        - ``description``: 工具描述。
        - ``parameters``: JSON Schema 参数定义。
        - ``category``: 工具分类枚举。
        - ``_Invoke()``: 同步执行逻辑（返回 ToolResult）。

    Example::

        @ToolComponent.Register
        class ReadFileTool(BaseTool):
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

            def _Invoke(self, filePath: str) -> ToolResult:
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

    timeout: float | None = None
    """工具执行超时秒数，None 表示不设限制。子类可覆盖此值。

    例如：文件读取 30s、网络请求 60s、Shell 命令 300s。
    """

    resultLodLevel: EContextLodLevel | None = EContextLodLevel.EXTERNAL_ONLY
    """工具结果注入上下文的 LOD 等级，默认 EXTERNAL_ONLY（当轮注入、次轮丢弃）。

    子类覆盖以控制结果持久化策略：
    - SUMMARIZABLE (LOD1)：可压缩不可丢弃（如 load_skill 返回的 SOP）。
    - DISCARDABLE (LOD2)：可压缩可丢弃（旧工具结果）。
    - EXTERNAL_ONLY (LOD3)：当轮注入、次轮丢弃（默认值）。
    """

    skipPersist: bool = False
    """是否跳过大结果落盘。子类覆盖为 True 表示结果已在磁盘上无需二次落盘。

    例如：read_file 读取的文件本身已在磁盘，不需要再写入 ContentStore。
    """

    # ---- 子类覆盖: 执行逻辑 ----

    def _Invoke(self, **kwargs) -> ToolResult:
        """同步执行逻辑 —— 子类覆盖此方法实现纯同步操作。

        文件读写、内存计算等操作仅需实现此方法。
        返回值自动被 _InvokeAsync 在线程池中异步包装。

        Args:
            **kwargs: 与 parameters 定义对应的关键字参数。

        Returns:
            ToolResult: 统一执行结果。

        Raises:
            NotImplementedError: 子类未实现 _Invoke 或 _InvokeAsync。
        """
        raise NotImplementedError(
            f"{self.__class__.__name__}: must implement _Invoke() or _InvokeAsync()"
        )

    async def _InvokeAsync(self, **kwargs) -> ToolResult:
        """异步执行逻辑 —— 默认回退到 _Invoke。

        异步操作（subprocess、网络请求等）覆盖此方法避免阻塞事件循环。
        默认实现在线程池中执行 _Invoke，保证 ExecuteAsync 始终异步兼容。

        Args:
            **kwargs: 与 parameters 定义对应的关键字参数。

        Returns:
            ToolResult: 统一执行结果。
        """
        import asyncio
        return await asyncio.to_thread(self._Invoke, **kwargs)

    async def ExecuteAsync(self, **kwargs) -> ToolResult:
        """公共异步执行入口 —— 优先 _InvokeAsync，回退 _Invoke。

        外部只需调用此方法，无需关心底层是同步还是异步实现。

        Args:
            **kwargs: 与 parameters 定义对应的关键字参数。

        Returns:
            ToolResult: 统一执行结果。
        """
        return await self._InvokeAsync(**kwargs)

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

    # ---- 安全工具方法 ----

    @staticmethod
    def _SanitizePath(path: str, allowedRoot: str) -> str:
        """规范化路径并验证在 allowedRoot 内，防止路径遍历攻击。

        Args:
            path: 待校验的原始路径（可为相对或绝对）。
            allowedRoot: 允许的根目录（绝对路径）。

        Returns:
            规范化后的绝对路径。

        Raises:
            ValueError: 路径越界（解析后逸出 allowedRoot）。
        """
        resolved = os.path.realpath(os.path.abspath(path))
        root = os.path.realpath(os.path.abspath(allowedRoot))
        if not resolved.startswith(root + os.sep) and resolved != root:
            raise ValueError(
                f"Path traversal blocked: {path} resolves outside allowed root"
            )
        return resolved

    @staticmethod
    def _GetAllowedRoot() -> str:
        """获取路径校验的允许根目录。

        当前实现：返回 os.getcwd() 作为 fallback。
        Tool 实例若持有 Agent 引用，可在子类覆盖以返回 AgentConfig.workspaceRoot。
        """
        return os.getcwd()

    # ---- 魔法方法 ----

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r}, category={self.category.value})"
