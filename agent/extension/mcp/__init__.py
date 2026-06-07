"""Agent Extension MCP —— MCP Server 配置管理模块。

对标 Claude Code MCP 的 claude mcp add/remove/list 命令体系，提供：
    - EMcpTransport: 三种传输协议枚举（Stdio / Http / Sse）。
    - McpServerConfig: 单个 Server 的连接配置对象。
    - McpServerRegistry: 注册表，支持 .mcp.json 加载。
"""

from .eMcpTransport import EMcpTransport
from .mcpServerConfig import McpServerConfig
from .mcpServerRegistry import McpServerRegistry

__all__ = [
    "EMcpTransport",
    "McpServerConfig",
    "McpServerRegistry",
]
