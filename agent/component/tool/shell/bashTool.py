"""Shell 命令执行工具 —— 在终端中执行命令并返回输出，含安全沙箱校验。"""

from __future__ import annotations

import os
import re
import shlex

from ..baseTool import BaseTool
from ..eToolCategory import EToolCategory
from ..toolResult import ToolResult
from ..tool import ToolComponent

MAX_OUTPUT_LENGTH = 50000

# ---- 安全沙箱常量 ----

# 允许的安全命令白名单（命令基名）
_DEFAULT_ALLOWED_COMMANDS: set[str] = {
    # 开发工具
    "python", "python3", "node", "npm", "npx", "pnpm", "yarn", "go", "rustc", "cargo",
    "javac", "java", "gcc", "g++", "make", "cmake", "dotnet",
    # 版本控制
    "git", "svn",
    # 包管理
    "pip", "pip3", "conda", "gem", "cargo", "composer",
    # 文件操作
    "ls", "dir", "cat", "type", "head", "tail", "find", "grep",
    "echo", "wc", "sort", "uniq", "cut", "sed", "awk",
    # 系统信息
    "pwd", "whoami", "hostname", "date", "uname", "env",
    # 测试
    "pytest", "jest", "mocha", "go test",
    # 构建
    "tsc", "esbuild", "webpack", "vite", "rollup",
}

# 危险命令黑名单（完整匹配或前缀匹配）
_DEFAULT_BLOCKED_COMMANDS: set[str] = {
    "rm", "rmdir", "del", "deltree",
    "format", "fdisk", "diskpart",
    "shutdown", "reboot", "halt", "poweroff",
    "mkfs", "fsck", "mount", "umount",
    "chmod", "chown", "chgrp",
    "kill", "killall", "pkill",
    "wget", "curl",
    "sudo", "su", "runas",
    "scp", "sftp", "nc", "netcat",
    "eval", "exec", "source",
    "systemctl", "service",
    "docker", "podman",
    "iptables", "netsh",
}

# 危险模式正则（匹配命令行中的危险操作）
_DANGEROUS_PATTERNS: list[re.Pattern] = [
    # 强制删除
    re.compile(r"\brm\s+-rf\b", re.IGNORECASE),
    re.compile(r"\brm\s+-r\s*-f\b", re.IGNORECASE),
    re.compile(r"\bdel\s+/[fq]\b", re.IGNORECASE),
    # 磁盘操作
    re.compile(r">\s*/dev/", re.IGNORECASE),
    re.compile(r"\bdd\s+if=", re.IGNORECASE),
    # 网络下载
    re.compile(r"\b(curl|wget)\s+.*\|\s*(ba)?sh", re.IGNORECASE),
    # fork bomb
    re.compile(r":\(\s*\)\s*\{\s*:"),
    re.compile(r"%\(0\|%0\)"),
    # 环境变量注入
    re.compile(r"\bPATH\s*=", re.IGNORECASE),
    # 权限提升
    re.compile(r"\bsudo\b", re.IGNORECASE),
    # 命令替换（$()、反引号）—— 绕过白名单的主要手段
    re.compile(r"\$\("),
    re.compile(r"`"),
    # 进程替换
    re.compile(r"<\("),
    # 写入系统关键路径
    re.compile(r">\s*/(etc|bin|sbin|usr|boot|sys|proc)/", re.IGNORECASE),
]

# Shell 控制操作符，用于将复合命令拆分为独立子命令逐段校验
_SEGMENT_SPLIT_RE = re.compile(r"&&|\|\||[|;&\n]")


@ToolComponent.Register
class BashTool(BaseTool):
    """在终端中执行 Shell 命令并捕获输出，含安全沙箱校验。

    安全策略（三级）：
    1. 命令白名单：仅允许 _DEFAULT_ALLOWED_COMMANDS 中的命令。
    2. 命令黑名单：拦截 _DEFAULT_BLOCKED_COMMANDS 中的危险命令。
    3. 模式匹配：正则扫描 _DANGEROUS_PATTERNS，拦截危险操作模式。

    可通过扩展 allowedCommands / blockedCommands / dangerousPatterns 自定义策略，
    设置 sandboxEnabled = False 可关闭沙箱（仅在受控环境中使用）。
    """

    name: str = "bash"
    description: str = (
        "Execute a shell command in the terminal and return the output. "
        "Use for running build commands, tests, git operations, package management, "
        "or any CLI tool. Commands are validated against a security sandbox."
    )
    category: EToolCategory = EToolCategory.SHELL
    timeout: float | None = 120.0
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

    # ---- 安全配置（可按需扩展） ----

    sandboxEnabled: bool = True
    """是否启用安全沙箱，仅在受控环境中可关闭。"""

    allowedCommands: set[str] = _DEFAULT_ALLOWED_COMMANDS.copy()
    """安全命令白名单。"""

    blockedCommands: set[str] = _DEFAULT_BLOCKED_COMMANDS.copy()
    """危险命令黑名单。"""

    dangerousPatterns: list[re.Pattern] = list(_DANGEROUS_PATTERNS)
    """危险模式正则列表。"""

    workingDir: str = ""
    """限制命令执行目录，空字符串表示不限制。"""

    # ---- 执行逻辑 ----

    async def _InvokeAsync(self, command: str, timeout: int = 120) -> ToolResult:
        import asyncio

        # ---- 安全校验 ----
        if self.sandboxEnabled:
            validationError = self._ValidateCommand(command)
            if validationError:
                return ToolResult.Fail(
                    f"Command rejected by security sandbox: {validationError}\n"
                    f"Blocked command: {command[:200]}",
                    toolName=self.name,
                )

        # ---- Shell 转义防护 ----
        try:
            safeArgs = shlex.split(command)
            if not safeArgs:
                return ToolResult.Fail("Empty command", toolName=self.name)
        except ValueError as exc:
            return ToolResult.Fail(
                f"Command parsing failed: {exc}", toolName=self.name
            )

        # ---- 工作目录限制 ----
        cwd = self.workingDir or None

        # ---- 不允许空命令 ----
        if not command.strip():
            return ToolResult.Fail("Empty command", toolName=self.name)

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
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

    # ---- 安全校验 ----

    def _ValidateCommand(self, command: str) -> str:
        """校验命令安全性，返回空字符串表示通过，否则返回拒绝原因。

        校验顺序：
        1. 危险模式正则匹配（含命令替换、进程替换等绕过手段）
        2. 逐子命令段校验黑名单（按 &&、||、|、;、& 拆分，防止 `echo ok && rm -rf ~` 绕过）
        3. 逐子命令段校验白名单（仅当白名单非空时）

        早期实现仅校验首个命令却执行整条原始串，可被 `&&` / `$()` 等轻易绕过，
        此处对每个子命令段独立校验，确保复合命令的每一段都在策略允许范围内。
        """
        if not command.strip():
            return "Empty command"

        # 1. 危险模式正则匹配（整条命令行）
        for pattern in self.dangerousPatterns:
            if pattern.search(command):
                return f"Command matches dangerous pattern: {pattern.pattern}"

        # 2 & 3. 逐子命令段校验黑/白名单
        segments = self._ExtractBaseCommands(command)
        if not segments:
            return "Empty command"

        for baseCommand in segments:
            if baseCommand in self.blockedCommands:
                return f"Command '{baseCommand}' is in the blocked list"
            if self.allowedCommands and baseCommand not in self.allowedCommands:
                return (
                    f"Command '{baseCommand}' is not in the allowed list. "
                    f"Allowed: {', '.join(sorted(self.allowedCommands))}"
                )

        return ""

    @classmethod
    def _ExtractBaseCommands(cls, command: str) -> list[str]:
        """将复合命令拆分为各子命令段，提取每段的基命令名（小写、去路径）。

        按 Shell 控制操作符（&&、||、|、;、&、换行）拆分，对每段提取基名。

        例: 'echo ok && /usr/bin/git status | grep x'
            → ['echo', 'git', 'grep']
        """
        bases: list[str] = []
        for segment in _SEGMENT_SPLIT_RE.split(command):
            base = cls._ExtractSegmentBase(segment)
            if base:
                bases.append(base)
        return bases

    @staticmethod
    def _ExtractSegmentBase(segment: str) -> str:
        """提取单个子命令段的基名称（去除路径与参数）。

        例: '/usr/bin/git status' → 'git'；'npm install' → 'npm'。
        """
        stripped = segment.strip()
        if not stripped:
            return ""

        try:
            parts = shlex.split(stripped)
            base = parts[0] if parts else ""
        except ValueError:
            tokens = stripped.split()
            base = tokens[0] if tokens else ""

        if not base:
            return ""
        return os.path.basename(base).lower()
