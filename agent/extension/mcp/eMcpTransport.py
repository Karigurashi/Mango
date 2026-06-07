"""MCP 传输协议枚举 —— 对标 Claude Code MCP 的三种传输方式。"""

from enum import Enum


class EMcpTransport(Enum):
    """MCP Server 通信的传输协议。

    Attributes:
        STDIO: 本地子进程，通过 stdin/stdout 通信（最常用）。
        HTTP: 远程服务，通过 streamable HTTP 通信（推荐用于远程）。
        SSE: 远程服务，通过 Server-Sent Events 通信（已废弃，向后兼容）。
    """

    STDIO = "stdio"
    HTTP = "http"
    SSE = "sse"
