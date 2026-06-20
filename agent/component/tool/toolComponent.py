"""ToolComponent —— 将 Tool 注册与调度封装为可挂载的 IComponent。

挂载到 BaseAgent 后，通过 BaseAgent.GetComponent(ToolComponent) 获取工具注册表，
支持装饰器注册、外部扩展、LLM 工具绑定、调度分发。
对标 Claude Code Tool 调度机制。
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, TYPE_CHECKING

from agent.core.baseComponent import IComponent
from common.logger import Logger
from llm.provider.chatMessage import ToolSpec, ToolCall

from .eToolCategory import EToolCategory
from .toolResult import ToolResult

if TYPE_CHECKING:
    from .baseTool import BaseTool
    from agent.core.baseAgent import BaseAgent


class ToolComponent(IComponent):
    """Tool 管理组件 —— 持有工具注册表并实现调度分发。

    挂载到 BaseAgent 后自动可用，通过 GetComponent(ToolComponent) 获取。
    对标 Claude Code Tool 调度机制：
    - 装饰器注册：@ToolComponent.Register 自动注册工具类。
    - 外部注册：RegisterTool() 接受已实例化的工具对象。
    - ToolSpec 导出：GetAllToolSpecs() 直接给 LLMClient.BindTools() 使用。
    - 调度分发：DispatchAsync() 根据 LLM ToolCall 查找工具并异步执行（含超时控制）。

    用法::

        from agent.component.tool.toolComponent import ToolComponent

        toolComp = ToolComponent()
        agent.AddComponent(toolComp)
        toolComp.LoadBuiltins()

        # 方式一：装饰器注册（推荐）
        @ToolComponent.Register
        class ReadFileTool(BaseTool):
            name = "read_file"
            ...

        # 方式二：外部实例注册
        toolComp.RegisterTool(myCustomTool)

        # 绑定到 LLM
        specs = toolComp.GetAllToolSpecs()
        llmClient.BindTools(specs)

        # 分发 LLM ToolCall
        result = await toolComp.DispatchAsync(toolCall)
    """

    # ---- 类级状态（装饰器注册共享） ----

    _toolClasses: dict[str, type["BaseTool"]] = {}
    """类级工具类注册表，供 @ToolComponent.Register 装饰器使用。
    所有 ToolComponent 实例共享此注册表，确保装饰器在 import 时生效。"""

    # ---- 实例初始化 ----

    def __init__(self) -> None:
        self._tools: dict[str, "BaseTool"] = {}
        """实例级工具实例注册表，隔离不同 Agent 的工具实例。"""
        self._defaultTimeout: float | None = 300.0
        """全局默认工具超时秒数，None 表示不设限制。单工具可通过 timeout 类属性覆盖。"""
        self._executionStats: dict[str, list[float]] = {}
        """每个工具的执行耗时列表（仅保留最近 100 次）。"""
        self._executionStatsLimit: int = 100

    # ---- 生命周期 ----

    def OnInitialize(self, agent: BaseAgent) -> None:
        """挂载后初始化。"""
        pass

    def OnDestroy(self) -> None:
        """从 BaseAgent 卸载时回调，清空所有已注册工具实例。"""
        self._tools.clear()

    # ---- 装饰器注册（类方法） ----

    @classmethod
    def Register(cls, toolClass: type["BaseTool"]) -> type["BaseTool"]:
        """装饰器：将工具类注册到全局表。

        工具类必须声明 ``name`` 类属性。

        Returns:
            原样返回工具类，不改变其行为。
        """
        toolName = getattr(toolClass, "name", "")
        if not toolName:
            raise ValueError(f"{toolClass.__name__} must define a non-empty 'name' class attribute")
        cls._toolClasses[toolName] = toolClass
        return toolClass

    # ---- 外部实例注册 ----

    def RegisterTool(self, tool: "BaseTool") -> None:
        """注册已实例化的工具对象（用于外部扩展）。

        Args:
            tool: 已实例化的 BaseTool 子类对象。
        """
        if not tool.name:
            raise ValueError("Tool must have a non-empty name")
        self._tools[tool.name] = tool

    def RegisterTools(self, tools: list["BaseTool"]) -> None:
        """批量注册工具实例。"""
        for tool in tools:
            self.RegisterTool(tool)

    # ---- 注销 ----

    def Unregister(self, name: str) -> None:
        """移除指定工具（从实例注册中移除）。"""
        self._tools.pop(name, None)

    # ---- 查询 ----

    def Get(self, name: str) -> "BaseTool | None":
        """按名称获取工具实例。

        优先返回已实例化的工具，其次从注册类创建并缓存实例，
        确保同一名称始终返回同一实例。
        """
        if name in self._tools:
            return self._tools[name]

        toolClass = self._toolClasses.get(name)
        if toolClass is not None:
            instance = toolClass()
            self._tools[name] = instance  # 缓存实例，避免重复创建
            return instance

        return None

    def GetClass(self, name: str) -> type["BaseTool"] | None:
        """按名称获取工具类。"""
        return self._toolClasses.get(name)

    def GetAll(self) -> dict[str, "BaseTool"]:
        """获取所有工具实例（类注册的懒实例化并缓存，已注册实例直接复用）。"""
        # 先将未实例化的类注册工具懒实例化并缓存
        for name, toolClass in self._toolClasses.items():
            if name not in self._tools:
                self._tools[name] = toolClass()
        return dict(self._tools)

    def GetByCategory(self, category: EToolCategory) -> list["BaseTool"]:
        """按分类获取工具实例。"""
        result: list["BaseTool"] = []
        for tool in self.GetAll().values():
            if tool.category == category:
                result.append(tool)
        return result

    def GetByCategories(self, categories: list[EToolCategory]) -> list["BaseTool"]:
        """按多个分类获取工具实例。"""
        result: list["BaseTool"] = []
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
        """根据 LLM ToolCall 查找工具并异步执行（含超时控制）。

        超时优先级：工具实例 timeout > 工具类 timeout > 全局 _defaultTimeout。
        timeout 为 None 时不设超时限制。
        """
        tool = self.Get(toolCall.name)
        if tool is None:
            return ToolResult.Fail(
                f"Unknown tool '{toolCall.name}'. Available: {', '.join(sorted(self._allToolNames()))}",
                toolName=toolCall.name,
            )

        timeout = self._ResolveTimeout(tool)
        startTime = time.perf_counter()

        try:
            if timeout is not None:
                result = await asyncio.wait_for(
                    tool.ExecuteAsync(**toolCall.arguments),
                    timeout=timeout,
                )
            else:
                result = await tool.ExecuteAsync(**toolCall.arguments)
            elapsed = time.perf_counter() - startTime
            self._RecordExecution(toolCall.name, elapsed)
            return result.WithToolName(toolCall.name)
        except asyncio.TimeoutError:
            elapsed = time.perf_counter() - startTime
            self._RecordExecution(toolCall.name, elapsed)
            Logger.Warning(
                f"Tool '{toolCall.name}' timed out after {timeout}s"
            )
            return ToolResult.Fail(
                f"Tool '{toolCall.name}' execution timed out after {timeout}s",
                toolName=toolCall.name,
            )
        except Exception as exc:
            elapsed = time.perf_counter() - startTime
            self._RecordExecution(toolCall.name, elapsed)
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
        import asyncio as _asyncio
        tasks = [self.DispatchAsync(tc) for tc in toolCalls]
        return list(await _asyncio.gather(*tasks))

    # ---- 元数据 ----

    def GetAllToolInfo(self) -> list[dict[str, Any]]:
        """返回所有工具元数据，供可视化/调试。"""
        return [tool.GetToolInfo() for tool in self.GetAll().values()]

    # ---- 管理 ----

    def Count(self) -> int:
        """已注册工具总数（类注册 + 实例注册去重）。"""
        return len(self.GetAll())

    def Clear(self) -> None:
        """清空实例注册（谨慎使用），类注册不受影响。"""
        self._tools.clear()

    def LoadBuiltins(self) -> int:
        """加载所有内置工具。

        通过导入各工具模块触发 ``@ToolComponent.Register`` 装饰器注册到类级表。
        装饰器注册是幂等的（类级 _toolClasses 跨实例与 Clear() 持久），
        无需 importlib.reload（reload 非线程安全且会重复执行模块副作用）。

        Returns:
            加载的工具数量。
        """
        from .control import todoWriteTool  # noqa: F401
        from .file import (  # noqa: F401
            deleteFileTool,
            grepCodeTool,
            listDirTool,
            readFileTool,
            searchFileTool,
            writeFileTool,
        )
        from .network import fetchContentTool, searchWebTool  # noqa: F401
        from .shell import bashTool  # noqa: F401

        return self.Count()

    # ---- 内部 ----

    def _allToolNames(self) -> list[str]:
        """返回所有已注册工具名称（用于错误提示）。"""
        return list(self._toolClasses.keys()) + [
            name for name in self._tools if name not in self._toolClasses
        ]

    def _ResolveTimeout(self, tool: "BaseTool") -> float | None:
        """解析工具超时值。

        优先级：工具实例 timeout > 工具类 timeout > 全局 _defaultTimeout。
        """
        instanceTimeout = getattr(tool, "timeout", None)
        if instanceTimeout is not None:
            return instanceTimeout

        toolClass = self._toolClasses.get(tool.name)
        if toolClass is not None:
            classTimeout = getattr(toolClass, "timeout", None)
            if classTimeout is not None:
                return classTimeout

        return self._defaultTimeout

    def SetDefaultTimeout(self, seconds: float | None) -> None:
        """设置全局默认工具超时（秒），None 表示不设限制。"""
        self._defaultTimeout = seconds

    # ---- 执行统计 ----

    def _RecordExecution(self, toolName: str, elapsed: float) -> None:
        """记录工具一次调度的耗时，每个工具仅保留最近 ``_executionStatsLimit`` 条。"""
        bucket = self._executionStats.setdefault(toolName, [])
        bucket.append(elapsed)
        excess = len(bucket) - self._executionStatsLimit
        if excess > 0:
            del bucket[:excess]

    def GetExecutionStats(self) -> dict[str, dict[str, float]]:
        """返回每个工具的执行耗时聚合指标。

        Returns:
            ``{toolName: {count, avg, max, min, last}}`` 结构的字典。
        """
        stats: dict[str, dict[str, float]] = {}
        for name, samples in self._executionStats.items():
            if not samples:
                continue
            stats[name] = {
                "count": float(len(samples)),
                "avg": sum(samples) / len(samples),
                "max": max(samples),
                "min": min(samples),
                "last": samples[-1],
            }
        return stats

    # ---- 魔法方法 ----

    def __repr__(self) -> str:
        return f"ToolComponent(tools={self.Count()})"

    def __contains__(self, name: str) -> bool:
        return name in self._tools or name in self._toolClasses
