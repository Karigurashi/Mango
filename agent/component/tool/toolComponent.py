"""ToolComponent —— 将 Tool 注册与调度封装为可挂载的 IComponent。

挂载到 BaseAgent 后，通过 BaseAgent.GetComponent(ToolComponent) 获取工具注册表，
支持装饰器注册、外部扩展、LLM 工具绑定、调度分发。
对标 Claude Code Tool 调度机制。
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Any, TYPE_CHECKING

from agent.core.baseComponent import IComponent
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
        self._disabled: set[str] = set()
        """实例级禁用工具名称集合，被禁用的工具不会出现在 GetAll/GetAllToolSpecs 等查询中。"""
        self._defaultTimeout: float | None = 300.0
        """全局默认工具超时秒数，None 表示不设限制。单工具可通过 timeout 类属性覆盖。"""
        self._executionStats: dict[str, deque[float]] = {}
        """每个工具的执行耗时队列（仅保留最近 100 次）。"""
        self._executionStatsLimit: int = 100

    # ---- 生命周期 ----

    def OnInitialize(self, agent: BaseAgent) -> None:
        """挂载后初始化，持有 Agent 引用供工具调度时注入。"""
        self._agent = agent

    def OnDestroy(self) -> None:
        """从 BaseAgent 卸载时回调，调用各工具清理钩子并清空实例。"""
        for tool in self._tools.values():
            try:
                tool.OnDestroy()
            except Exception:
                pass
        self._tools.clear()
        self._agent = None

    # ---- 装饰器注册（类方法） ----

    @classmethod
    def Register(cls, toolClass: type["BaseTool"]) -> type["BaseTool"]:
        """装饰器：将工具类注册到全局表。

        工具类必须声明 ``name`` 类属性。

        Returns:
            原样返回工具类，不改变其行为。
        """
        toolName = toolClass.name
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

    # ---- 禁用 / 启用 ----

    def Disable(self, name: str) -> None:
        """禁用一个工具，使其不出现在 GetAll/GetAllToolSpecs 等查询结果中。

        仅影响当前 ToolComponent 实例，不影响其他实例或类级注册表。
        对已通过 RegisterTool 注册的实例工具同样生效。
        """
        self._disabled.add(name)

    def DisableByCategory(self, category: EToolCategory) -> None:
        """按分类批量禁用工具。

        会遍历类级注册表 _toolClasses 和实例注册表 _tools，
        将匹配 category 的工具名加入禁用集。
        """
        for toolName, toolClass in self._toolClasses.items():
            if toolClass.category == category:
                self._disabled.add(toolName)
        for toolName, tool in self._tools.items():
            if tool.category == category:
                self._disabled.add(toolName)

    def EnableByCategory(self, category: EToolCategory) -> None:
        """按分类批量启用工具，对标 DisableByCategory 的逆操作。"""
        for toolName, toolClass in self._toolClasses.items():
            if toolClass.category == category:
                self._disabled.discard(toolName)
        for toolName, tool in self._tools.items():
            if tool.category == category:
                self._disabled.discard(toolName)

    def Enable(self, name: str) -> None:
        """重新启用一个已被禁用的工具。"""
        self._disabled.discard(name)

    def IsEnabled(self, name: str) -> bool:
        """检查指定工具当前是否启用。"""
        return name not in self._disabled

    def GetDisabled(self) -> set[str]:
        """返回当前被禁用的工具名称集合（副本）。"""
        return set(self._disabled)

    # ---- 查询 ----

    def Get(self, name: str) -> "BaseTool | None":
        """按名称获取工具实例。

        优先返回已实例化的工具，其次从注册类创建并缓存实例，
        确保同一名称始终返回同一实例。
        被 Disable 的工具返回 None，视同不存在。
        """
        if name in self._disabled:
            return None

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

    def _EnsureAllInstantiated(self) -> None:
        """将未实例化的类注册工具懒实例化并缓存到实例表。

        幂等操作：已实例化的工具跳过，仅处理新增的类注册项。
        被 Disable 的工具跳过不实例化。
        """
        for name, toolClass in self._toolClasses.items():
            if name not in self._disabled and name not in self._tools:
                self._tools[name] = toolClass()

    def GetAll(self) -> dict[str, "BaseTool"]:
        """获取所有工具实例（确保类注册工具已实例化后返回快照）。"""
        self._EnsureAllInstantiated()
        return dict(self._tools)

    def GetByCategory(self, category: EToolCategory) -> list["BaseTool"]:
        """按分类获取工具实例。"""
        self._EnsureAllInstantiated()
        result: list["BaseTool"] = []
        for tool in self._tools.values():
            if tool.category == category:
                result.append(tool)
        return result

    def GetByCategories(self, categories: list[EToolCategory]) -> list["BaseTool"]:
        """按多个分类获取工具实例。"""
        self._EnsureAllInstantiated()
        catSet = set(categories)
        result: list["BaseTool"] = []
        for tool in self._tools.values():
            if tool.category in catSet:
                result.append(tool)
        return result

    # ---- ToolSpec 导出 ----

    def GetAllToolSpecs(self) -> list[ToolSpec]:
        """获取所有工具的 ToolSpec 列表，可直接传给 LLMClient.BindTools()。

        Returns:
            ToolSpec 列表，可用于 LLM function calling 绑定。
        """
        self._EnsureAllInstantiated()
        return [tool.ToToolSpec() for tool in self._tools.values()]

    def GetToolSpecsByCategory(self, category: EToolCategory) -> list[ToolSpec]:
        """按分类获取 ToolSpec。"""
        self._EnsureAllInstantiated()
        return [tool.ToToolSpec() for tool in self._tools.values() if tool.category == category]

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

        # 注入 Agent 引用，使工具可通过 self._agent 访问 Agent 及组件
        tool._agent = self._agent

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
        """批量并发分发多个工具调用，异常隔离：单工具失败不取消其余任务。

        Args:
            toolCalls: LLM 返回的多个 ToolCall。

        Returns:
            与输入顺序对应的 ToolResult 列表。
        """
        async def _SafeDispatch(tc: ToolCall) -> ToolResult:
            try:
                return await self.DispatchAsync(tc)
            except Exception as exc:
                return ToolResult.Fail(
                    f"Tool execution error: {exc}",
                    toolName=tc.name,
                )

        tasks = [_SafeDispatch(tc) for tc in toolCalls]
        return list(await asyncio.gather(*tasks))

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

    # ---- 内部 ----

    def _allToolNames(self) -> list[str]:
        """返回所有已启用工具名称（用于错误提示）。"""
        return [
            name for name in self._toolClasses if name not in self._disabled
        ] + [
            name for name in self._tools
            if name not in self._toolClasses and name not in self._disabled
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
        """记录工具一次调度的耗时，每个工具仅保留最近 ``_executionStatsLimit`` 条。

        使用 deque(maxlen=N) 自动淘汰旧数据，O(1) 追加无需 del。
        """
        bucket = self._executionStats.get(toolName)
        if bucket is None:
            bucket = deque(maxlen=self._executionStatsLimit)
            self._executionStats[toolName] = bucket
        bucket.append(elapsed)

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
        return name not in self._disabled and (name in self._tools or name in self._toolClasses)


# 文件末尾触发 @Register 装饰器注册，必须在类定义完成后导入，避免循环依赖
from .control import (  # noqa: F401, E402
    todoWriteTool,
    runWorkflowTool,
    getWorkflowSchemaTool,
    listWorkflowsTool,
    cancelWorkflowTool,
)
from .file import (  # noqa: F401, E402
    deleteFileTool,
    globTool,
    grepTool,
    readTool,
    searchCodebaseTool,
    searchReplaceTool,
    writeTool,
)
from .network import webFetchTool, webSearchTool  # noqa: F401, E402
from .shell import shellTool, getTerminalOutputTool  # noqa: F401, E402
