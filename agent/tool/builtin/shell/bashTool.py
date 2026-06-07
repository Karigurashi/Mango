"""Shell 命令执行工具 —— 在终端中执行命令并返回输出。"""

from __future__ import annotations

from ...abstractTool import AbstractTool
from ...eToolCategory import EToolCategory
from ...toolResult import ToolResult
from ...toolRegistry import G_ToolRegistry

MAX_OUTPUT_LENGTH = 50000


@G_ToolRegistry.Register
class BashTool(AbstractTool):
    """在终端中执行 Shell 命令并捕获输出。

    支持超时控制，输出长度截断保护。
    """

    name: str = "bash"
    description: str = (
        "Execute a shell command in the terminal and return the output. "
        "Use this for running build commands, tests, git operations, package management, "
        "or any CLI tool. The command runs in a subprocess with a timeout."
    )
    category: EToolCategory = EToolCategory.SHELL
    parameters: dict = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute",
            },
            "timeout": {
                "type": "integer",
                "description": "Optional. Timeout in seconds (default 120)",
            },
        },
        "required": ["command"],
    }

    async def _ainvoke(self, command: str, timeout: int = 120) -> ToolResult:
        import asyncio

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return ToolResult.Fail(
                    f"Command timed out after {timeout}s: {command[:200]}",
                    toolName=self.name,
                )

            output = (stdout or b"").decode("utf-8", errors="replace")
            errorOutput = (stderr or b"").decode("utf-8", errors="replace")

            parts: list[str] = []
            if output:
                if len(output) > MAX_OUTPUT_LENGTH:
                    output = output[:MAX_OUTPUT_LENGTH] + "\n... (output truncated)"
                parts.append(output)
            if errorOutput:
                if len(errorOutput) > MAX_OUTPUT_LENGTH:
                    errorOutput = errorOutput[:MAX_OUTPUT_LENGTH] + "\n... (stderr truncated)"
                parts.append(f"[stderr]\n{errorOutput}")

            resultText = "\n".join(parts) if parts else "(no output)"
            resultText = f"[Exit code: {proc.returncode}]\n{resultText}"

            return ToolResult.Ok(resultText, toolName=self.name)

        except Exception as exc:
            return ToolResult.Fail(
                f"Command execution failed: {exc}\nCommand: {command[:200]}",
                toolName=self.name,
            )
