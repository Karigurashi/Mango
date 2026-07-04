"""Agent CLI 终端模块 —— 对标 Claude Code 交互模式的 REPL 终端。

提供 CliApp 主编排器、CliRenderer 流式渲染引擎、斜杠指令系统、
ANSI 主题配置与状态机。

Usage::

    from agent.cli import CliApp
    app = CliApp("deepseek-high")
    app.Run()
"""

from .cliApp import CliApp
from .cliCommand import CliCommand, CliContext
from .cliCommandRegistry import CliCommandRegistry
from .cliConfig import CliConfig
from .cliRenderer import CliRenderer
from .eCliState import ECliState

__all__ = [
    "CliApp",
    "CliCommand",
    "CliContext",
    "CliCommandRegistry",
    "CliConfig",
    "CliRenderer",
    "ECliState",
]
