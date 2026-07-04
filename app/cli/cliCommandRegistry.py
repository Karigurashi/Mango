"""CliCommandRegistry —— 斜杠指令注册与分发。

维护 name/alias → CliCommand 的映射表，解析 "/command arg1 arg2"
格式输入并异步分发到对应 handler。
"""

from __future__ import annotations

from .cliCommand import CliCommand, CliContext


class CliCommandRegistry:
    """斜杠指令注册表 —— 注册、查询与异步分发。

    用法::

        registry = CliCommandRegistry()
        registry.Register(CliCommand("help", "Show help", _HelpCommand))
        handled = await registry.DispatchAsync("/help", ctx)
    """

    def __init__(self) -> None:
        self._lookup: dict[str, CliCommand] = {}  # name/alias → CliCommand
        self._commands: list[CliCommand] = []       # 去重后的命令列表

    # ---- 注册 ----

    def Register(self, command: CliCommand) -> None:
        """注册一条指令及其别名。

        重复注册同名指令会替换旧映射。

        Args:
            command: CliCommand 实例。
        """
        # 移除已存在的同名/同别名映射，防止 _commands 中累积重复
        self._commands = [c for c in self._commands if c.name != command.name]
        self._commands.append(command)
        self._lookup[command.name] = command
        for alias in command.aliases:
            self._lookup[alias] = command

    # ---- 分发 ----

    async def DispatchAsync(self, userInput: str, ctx: CliContext) -> bool:
        """解析并分发斜杠指令。

        输入格式: ``/command arg1 arg2``

        Args:
            userInput: 含 / 前缀的完整输入。
            ctx: 命令处理上下文。

        Returns:
            是否成功匹配到指令。
        """
        parts = userInput[1:].split(None, 1)  # 去掉 / 并按空白拆分为最多两部分
        name = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        command = self._lookup.get(name)
        if command is None:
            ctx.PrintError(f"Unknown command: /{name}. Type /help for available commands.")
            return False

        await command.handler(ctx, args)
        return True

    # ---- 查询 ----

    def GetCommands(self) -> list[CliCommand]:
        """返回去重后的命令列表。"""
        return list(self._commands)

    def GetHelpText(self) -> str:
        """生成格式化的帮助文本，命令按名称排序。

        Returns:
            每行一条命令的格式: ``  /name (alias1, alias2)  - description``
        """
        lines: list[str] = []
        # 按 name 排序去重
        seen: set[str] = set()
        for cmd in sorted(self._commands, key=lambda c: c.name):
            if cmd.name in seen:
                continue
            seen.add(cmd.name)
            line = f"  /{cmd.name}"
            aliases = ", ".join(f"/{a}" for a in cmd.aliases)
            if aliases:
                line += f" ({aliases})"
            line += f"  - {cmd.description}"
            lines.append(line)
        return "\n".join(lines)
