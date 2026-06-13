"""McpStdioClient —— MCP stdio 传输客户端，基于 JSON-RPC 2.0 与本地子进程通信。

负责：启动 MCP Server 子进程、完成 initialize 握手、tools/list 发现工具、
tools/call 调用工具。消息按行分隔（newline-delimited JSON-RPC），请求/响应
通过 id 配对，期间出现的通知（无 id）被忽略。

仅支持 stdio 传输；http/sse 远程传输由 McpComponent 显式标注为暂不支持。
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Optional

from common.cancellationToken import CancellationToken
from common.logger import Logger

# stdout 单行可能较大（工具返回大结果），放宽 StreamReader 行长上限
_STREAM_LIMIT = 16 * 1024 * 1024
_PROTOCOL_VERSION = "2024-11-05"
_DEFAULT_READ_TIMEOUT = 120.0  # 单次 MCP 请求读取超时秒数


class McpStdioClient:
    """单个 stdio MCP Server 的 JSON-RPC 客户端。

    生命周期：StartAsync → InitializeAsync → ListToolsAsync / CallToolAsync → Terminate。
    所有请求经同一把锁串行化，避免 DispatchBatch 并发调用时读写流错乱。

    Attributes:
        serverName: 所属 MCP Server 名称。
    """

    def __init__(
        self,
        serverName: str,
        launchCommand: list[str],
        env: dict[str, str] | None = None,
        readTimeout: float = _DEFAULT_READ_TIMEOUT,
    ) -> None:
        self.serverName = serverName
        self._launchCommand = launchCommand
        self._env = env or {}
        self._readTimeout = readTimeout
        self._proc: asyncio.subprocess.Process | None = None
        self._stderrTask: asyncio.Task | None = None
        self._requestId = 0
        self._ioLock = asyncio.Lock()
        self._initialized = False

    # ---- 启动 / 关闭 ----

    async def StartAsync(
        self,
        cancellationToken: Optional[CancellationToken] = None,
    ) -> bool:
        """启动 MCP Server 子进程。

        Returns:
            是否启动成功。
        """
        if not self._launchCommand:
            return False

        mergedEnv = dict(os.environ)
        mergedEnv.update(self._env)

        try:
            self._proc = await asyncio.create_subprocess_exec(
                *self._launchCommand,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=mergedEnv,
                limit=_STREAM_LIMIT,
            )
        except (OSError, ValueError) as exc:
            Logger.Warning(f"MCP[{self.serverName}]: failed to start: {exc}")
            return False

        self._stderrTask = asyncio.ensure_future(self._DrainStderrAsync())
        return True

    def Terminate(self) -> None:
        """同步终止子进程（供 OnDestroy 等同步上下文调用）。"""
        if self._stderrTask is not None and not self._stderrTask.done():
            self._stderrTask.cancel()
        proc = self._proc
        if proc is not None and proc.returncode is None:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
        self._proc = None
        self._initialized = False

    # ---- 握手与能力 ----

    async def InitializeAsync(
        self,
        cancellationToken: Optional[CancellationToken] = None,
    ) -> bool:
        """执行 MCP initialize 握手并发送 initialized 通知。"""
        response = await self._RequestAsync(
            "initialize",
            {
                "protocolVersion": _PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "brain-agent", "version": "1.0"},
            },
            cancellationToken,
        )
        if response is None or "error" in response:
            Logger.Warning(f"MCP[{self.serverName}]: initialize failed: {response}")
            return False

        await self._NotifyAsync("notifications/initialized", {})
        self._initialized = True
        return True

    async def ListToolsAsync(
        self,
        cancellationToken: Optional[CancellationToken] = None,
    ) -> list[dict[str, Any]]:
        """tools/list 发现 Server 暴露的工具。

        Returns:
            工具描述字典列表，每项含 name / description / inputSchema。
        """
        response = await self._RequestAsync("tools/list", {}, cancellationToken)
        if response is None or "error" in response:
            Logger.Warning(f"MCP[{self.serverName}]: tools/list failed: {response}")
            return []
        result = response.get("result", {})
        tools = result.get("tools", [])
        return tools if isinstance(tools, list) else []

    async def CallToolAsync(
        self,
        toolName: str,
        arguments: dict[str, Any],
        cancellationToken: Optional[CancellationToken] = None,
    ) -> tuple[bool, str]:
        """tools/call 调用指定工具。

        Returns:
            (是否成功, 文本内容)。
        """
        response = await self._RequestAsync(
            "tools/call",
            {"name": toolName, "arguments": arguments},
            cancellationToken,
        )
        if response is None:
            return False, f"MCP[{self.serverName}]: no response from tool '{toolName}'"
        if "error" in response:
            return False, f"MCP error: {response['error']}"

        result = response.get("result", {})
        isError = bool(result.get("isError", False))
        text = self._ExtractContentText(result.get("content", []))
        return (not isError), text

    # ---- 内部 JSON-RPC ----

    async def _RequestAsync(
        self,
        method: str,
        params: dict[str, Any],
        cancellationToken: Optional[CancellationToken] = None,
    ) -> dict[str, Any] | None:
        """发送一个 JSON-RPC 请求并读取配对的响应。"""
        if self._proc is None or self._proc.stdin is None or self._proc.stdout is None:
            return None

        async with self._ioLock:
            self._requestId += 1
            requestId = self._requestId
            payload = {
                "jsonrpc": "2.0",
                "id": requestId,
                "method": method,
                "params": params,
            }

            try:
                self._proc.stdin.write((json.dumps(payload) + "\n").encode("utf-8"))
                await self._proc.stdin.drain()
            except (BrokenPipeError, ConnectionResetError) as exc:
                Logger.Warning(f"MCP[{self.serverName}]: write failed: {exc}")
                return None

            # 读取直到拿到匹配 id 的响应，跳过通知与无关消息
            while True:
                if cancellationToken is not None and cancellationToken.IsCancellationRequested:
                    return None
                try:
                    line = await asyncio.wait_for(
                        self._proc.stdout.readline(),
                        timeout=self._readTimeout,
                    )
                except asyncio.TimeoutError:
                    Logger.Warning(
                        f"MCP[{self.serverName}]: read timed out after {self._readTimeout:.0f}s "
                        f"waiting for response to '{method}'"
                    )
                    return None
                except (asyncio.LimitOverrunError, ValueError) as exc:
                    Logger.Warning(f"MCP[{self.serverName}]: read failed: {exc}")
                    return None
                if not line:
                    return None  # EOF，进程退出
                try:
                    message = json.loads(line.decode("utf-8").strip())
                except json.JSONDecodeError:
                    continue
                if message.get("id") == requestId:
                    return message

    async def _NotifyAsync(self, method: str, params: dict[str, Any]) -> None:
        """发送一个无需响应的 JSON-RPC 通知。"""
        if self._proc is None or self._proc.stdin is None:
            return
        payload = {"jsonrpc": "2.0", "method": method, "params": params}
        try:
            self._proc.stdin.write((json.dumps(payload) + "\n").encode("utf-8"))
            await self._proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            pass

    async def _DrainStderrAsync(self) -> None:
        """持续排空 stderr，避免管道缓冲写满导致子进程阻塞。"""
        if self._proc is None or self._proc.stderr is None:
            return
        while True:
            try:
                line = await self._proc.stderr.readline()
            except (asyncio.CancelledError, ValueError):
                return
            if not line:
                return
            Logger.Debug(f"MCP[{self.serverName}] stderr: {line.decode('utf-8', 'replace').rstrip()}")

    @staticmethod
    def _ExtractContentText(content: Any) -> str:
        """从 MCP tools/call 结果的 content 数组提取文本。"""
        if not isinstance(content, list):
            return str(content)
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
            elif isinstance(block, dict):
                parts.append(json.dumps(block, ensure_ascii=False))
        return "\n".join(parts)

    def __repr__(self) -> str:
        alive = self._proc is not None and self._proc.returncode is None
        return f"McpStdioClient(server={self.serverName!r}, alive={alive})"
