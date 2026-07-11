"""CliContext —— CLI 平台指令上下文，继承 CommandContext。

override Print/PrintDim 等方法实现即时终端输出（不缓冲），
其余组件访问、退出控制等均继承自 CommandContext。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.channel.commandContext import CommandContext

from .cliConfig import CliConfig
from .cliRenderer import CliRenderer

if TYPE_CHECKING:
    from app.channel.baseChannel import BaseChannel
    from app.channel.channelMessage import ChannelMessage
    from app.channel.commandRegistry import CommandRegistry
    from app.channel.groupContext import GroupContext


class CliContext(CommandContext):
    """CLI 平台指令上下文 —— 终端即时输出。

    与基类 CommandContext 的区别：
    - Print/PrintDim/PrintWarning/PrintError 直接写入终端（通过 CliRenderer），
      不累积到响应缓冲区，因此 HasResponse 始终为 False，
      BaseChannel._DispatchCommandAsync 不会调用 OnSendResponseAsync。
    - 额外提供 Config 属性访问 CliConfig（ANSI 主题、FormatK 等）。
    """

    def __init__(
        self,
        channel: BaseChannel,
        groupContext: GroupContext,
        message: ChannelMessage,
        registry: CommandRegistry,
        cliConfig: CliConfig,
        renderer: CliRenderer,
    ) -> None:
        super().__init__(channel, groupContext, message, registry)
        self._cliConfig: CliConfig = cliConfig
        self._renderer: CliRenderer = renderer

    # ---- CLI 配置 ----

    @property
    def Config(self) -> CliConfig:
        """CLI 终端渲染配置。"""
        return self._cliConfig

    # ---- 输出（override 基类，直接写终端，不缓冲） ----

    def Print(self, text: str) -> None:
        """打印信息行（青色图标）—— 直接写终端。"""
        self._renderer.PrintInfo(text)

    def PrintDim(self, text: str) -> None:
        """打印 dim 行 —— 直接写终端。"""
        self._renderer.PrintDim(text)

    def PrintWarning(self, text: str) -> None:
        """打印警告行（琥珀色）—— 直接写终端。"""
        self._renderer.PrintWarning(text)

    def PrintError(self, text: str) -> None:
        """打印错误行（红色）—— 直接写终端。"""
        self._renderer.PrintError(text)
