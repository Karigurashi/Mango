"""CliCommand + CliContext —— 斜杠指令定义与命令处理器上下文。

CliCommand 为数据载体，CliContext 提供 Agent 组件便捷访问。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Awaitable, Callable, TYPE_CHECKING

from agent.component.harness.harnessComponent import HarnessComponent
from agent.component.session.sessionComponent import SessionComponent
from agent.component.llm.llmComponent import LLMComponent
from agent.component.contex.contextComponent import ContextComponent
from agent.component.tool.toolComponent import ToolComponent
from agent.component.data.dataComponent import DataComponent

from .cliConfig import CliConfig
from .cliRenderer import CliRenderer

if TYPE_CHECKING:
    from agent.agent import Agent
    from .cliCommandRegistry import CliCommandRegistry


@dataclass
class CliCommand:
    """斜杠指令定义 —— 名称、描述、处理函数与别名。

    Attributes:
        name: 指令名（不含 / 前缀）。
        description: 简短描述，用于 /help 输出。
        handler: 异步处理函数，签名为 (CliContext, str) -> None。
        aliases: 可选别名（不含 / 前缀）。
    """

    name: str
    description: str
    handler: Callable[[CliContext, str], Awaitable[None]]
    aliases: list[str] = field(default_factory=list)


class CliContext:
    """命令处理器上下文，提供 Agent 组件便捷访问。

    命令 handler 通过此上下文访问 Agent、Session、LLM 等组件，
    以及 Print/PrintDim 等便捷输出方法。

    Usage::

        async def MyCommand(ctx: CliContext, args: str) -> None:
            ctx.Print(f"Current model: {ctx.LLM.modelName}")
            ctx.PrintDim(f"Session: {ctx.Session.ActiveSessionId}")
    """

    def __init__(
        self,
        agent: Agent,
        config: CliConfig,
        renderer: CliRenderer,
        registry: CliCommandRegistry,
    ) -> None:
        self._agent = agent
        self._config = config
        self._renderer = renderer
        self._registry = registry
        self._wantsExit = False

    # ---- 组件访问 ----

    @property
    def Agent(self) -> Agent:
        return self._agent

    @property
    def Session(self) -> SessionComponent:
        return self._agent.GetComponent(SessionComponent)

    @property
    def LLM(self) -> LLMComponent:
        return self._agent.GetComponent(LLMComponent)

    @property
    def Context(self) -> ContextComponent:
        return self._agent.GetComponent(ContextComponent)

    @property
    def Tools(self) -> ToolComponent:
        return self._agent.GetComponent(ToolComponent)

    @property
    def Data(self) -> DataComponent:
        return self._agent.GetComponent(DataComponent)

    @property
    def Harness(self) -> HarnessComponent:
        return self._agent.GetComponent(HarnessComponent)

    @property
    def Config(self) -> CliConfig:
        return self._config

    @property
    def Registry(self) -> CliCommandRegistry:
        return self._registry

    @property
    def WantsExit(self) -> bool:
        """是否已请求退出 CLI。"""
        return self._wantsExit

    def RequestExit(self) -> None:
        """请求退出 CLI 主循环。"""
        self._wantsExit = True

    # ---- 便捷输出 ----

    def Print(self, text: str) -> None:
        """打印信息行（绿色）。"""
        self._renderer.PrintInfo(text)

    def PrintDim(self, text: str) -> None:
        """打印 dim 行。"""
        self._renderer.PrintDim(text)

    def PrintWarning(self, text: str) -> None:
        """打印警告行（黄色）。"""
        self._renderer.PrintWarning(text)

    def PrintError(self, text: str) -> None:
        """打印错误行（红色）。"""
        self._renderer.PrintError(text)
