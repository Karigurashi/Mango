"""MCP Server 注册表 —— 管理 MCP Server 配置，支持注册、查询、按作用域筛选。"""

from __future__ import annotations

import json
import os
from typing import Any

from .eMcpTransport import EMcpTransport
from .mcpServerConfig import McpServerConfig


class McpServerRegistry:
    """按名称索引 MCP Server 配置的注册表，每个 Agent 持有一份独立实例。

    用法::

        registry = McpServerRegistry()

        config = McpServerConfig(
            name="my-db",
            transport=EMcpTransport.STDIO,
            command="npx",
            args=["@modelcontextprotocol/server-postgres", "postgresql://localhost/mydb"],
        )
        registry.Register(config)

        # 查询
        server = registry.Get("my-db")
        allStdio = registry.GetByTransport(EMcpTransport.STDIO)
    """

    def __init__(self) -> None:
        self._servers: dict[str, McpServerConfig] = {}

    # ---- 注册 ----

    def Register(self, config: McpServerConfig) -> None:
        """注册一个 MCP Server 配置（同名覆盖）。"""
        if not config.name:
            raise ValueError("McpServerConfig must have a non-empty name")
        self._servers[config.name] = config

    def Unregister(self, name: str) -> None:
        """移除指定 Server。"""
        self._servers.pop(name, None)

    # ---- 查询 ----

    def Get(self, name: str) -> McpServerConfig | None:
        """按名称获取 Server 配置。"""
        return self._servers.get(name)

    def GetAll(self) -> dict[str, McpServerConfig]:
        """获取所有已注册 Server 配置的副本。"""
        return dict(self._servers)

    def GetEnabled(self) -> list[McpServerConfig]:
        """获取所有已启用的 Server。"""
        return [s for s in self._servers.values() if s.enabled]

    def GetByTransport(self, transport: EMcpTransport) -> list[McpServerConfig]:
        """按传输协议筛选。"""
        return [s for s in self._servers.values() if s.transport == transport]

    def GetByScope(self, scope: str) -> list[McpServerConfig]:
        """按作用域筛选。"""
        return [s for s in self._servers.values() if s.scope == scope]

    # ---- 序列化 ----

    def ToMCPJson(self) -> str:
        """导出为 .mcp.json 兼容的 JSON 字符串。"""
        serversDict: dict[str, dict[str, Any]] = {}
        for name, config in self._servers.items():
            data = config.ToDict()
            data.pop("name", None)
            data.pop("enabled", None)
            serversDict[name] = data
        result = {"mcpServers": serversDict}
        return json.dumps(result, indent=2, ensure_ascii=False)

    def LoadFromMCPJson(self, filePath: str) -> int:
        """从 .mcp.json 文件加载所有 Server 配置。

        Returns:
            成功加载的 Server 数量。
        """
        if not os.path.isfile(filePath):
            return 0

        try:
            with open(filePath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return 0

        serversDict = data.get("mcpServers", {})
        count = 0
        for name, serverData in serversDict.items():
            if isinstance(serverData, dict):
                serverData["name"] = name
                config = McpServerConfig.FromDict(serverData)
                self.Register(config)
                count += 1

        return count

    # ---- Context 注入辅助 ----

    def GetToolDescriptions(self) -> str:
        """获取所有已启用 Server 的工具描述文本，用于注入 system prompt。

        Returns:
            格式化的工具清单文本。
        """
        enabled = self.GetEnabled()
        if not enabled:
            return "No MCP servers configured."

        lines = []
        for server in enabled:
            transportLabel = f"[{server.transport.value}]"
            lines.append(f"  - {server.name} {transportLabel}")
        return "\n".join(lines)

    # ---- 管理 ----

    def Count(self) -> int:
        """已注册 Server 总数。"""
        return len(self._servers)

    def Clear(self) -> None:
        """清空所有注册（谨慎使用）。"""
        self._servers.clear()

    # ---- 魔法方法 ----

    def __repr__(self) -> str:
        return f"McpServerRegistry(servers={len(self._servers)})"

    def __contains__(self, name: str) -> bool:
        return name in self._servers
