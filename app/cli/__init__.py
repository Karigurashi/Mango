"""Agent CLI 终端模块 —— 对标 Claude Code 交互模式的 REPL 终端。

基于 BaseChannel 框架，CliApp 作为 CLI 平台适配器：
单群模式（groupId="cli"），斜杠指令 + 普通消息 + Ctrl+C 取消。

Usage::

    from app.cli import CliApp
    app = CliApp("deepseek-high")
    app.Run()
"""

from ..channel import Command, CommandRegistry
from .cliApp import CliApp
from .cliCommand import CliContext
from .cliConfig import CliConfig
from .cliRenderer import CliRenderer
from .eCliState import ECliState

__all__ = [
    "CliApp",
    "CliContext",
    "CliConfig",
    "CliRenderer",
    "ECliState",
    "Command",
    "CommandRegistry",
]
