"""McpComponent —— 将 MCP Server 管理封装为可挂载的 IComponent。

挂载到 BaseAgent 后，通过 BaseAgent.GetComponent(McpComponent) 获取
MCP Server 注册表，支持 .mcp.json 加载与多种传输协议。
对标 Claude Code MCP 的 claude mcp add/remove/list 命令体系。
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional, TYPE_CHECKING

from agent.core.baseComponent import IComponent
from common.cancellationToken import CancellationToken
from common.logger import Logger

from .eMcpTransport import EMcpTransport
from .mcpServerConfig import McpServerConfig

if TYPE_CHECKING:
    from agent.core.baseAgent import BaseAgent
    from .mcpClient import McpStdioClient
    from .mcpTool import McpTool


class McpComponent(IComponent):
    """MCP Server 管理组件 —— 持有 MCP Server 配置注册表。

    挂载到 BaseAgent 后自动可用，通过 GetComponent(McpComponent) 获取。
    对标 Claude Code MCP 的 Server 管理：
    - 支持 stdio / http / sse 三种传输协议。
    - 支持 .mcp.json 批量加载。

    用法::

        agent = BaseAgent()
        mcpComp = McpComponent()
        agent.AddComponent(mcpComp)
        mcpComp.LoadFromMCPJson(".mcp.json")
    """

    def __init__(self) -> None:
        self._servers: dict[str, McpServerConfig] = {}
        self._clients: list["McpStdioClient"] = []

    # ---- 生命周期 ----

    def OnInitialize(self, agent: BaseAgent) -> None:
        """挂载后初始化。"""
        pass

    def OnDestroy(self) -> None:
        """从 BaseAgent 卸载时回调，终止全部 MCP 子进程并清空注册。"""
        for client in self._clients:
            client.Terminate()
        self._clients.clear()
        self._servers.clear()

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

    # ---- 真实连接与工具发现 ----

    async def ConnectAllAsync(
        self,
        cancellationToken: Optional[CancellationToken] = None,
    ) -> list["McpTool"]:
        """连接全部已启用的 stdio MCP Server，发现并适配其工具。

        逐个启动 Server 子进程、完成 initialize 握手、tools/list 发现工具，
        将每个远程工具包装为 McpTool 返回。任一 Server 失败仅记录日志并跳过，
        不影响其他 Server 与整体 Agent 构建。远程（http/sse）传输暂不支持。

        客户端引用被持有，OnDestroy 时统一终止子进程。

        Returns:
            可注入 ToolComponent 的 McpTool 列表。
        """
        from .mcpClient import McpStdioClient
        from .mcpTool import McpTool

        tools: list["McpTool"] = []
        for server in self.GetEnabled():
            if server.transport != EMcpTransport.STDIO:
                Logger.Warning(
                    f"MCP[{server.name}]: transport '{server.transport.value}' "
                    f"not supported yet (only stdio), skipped"
                )
                continue

            launchCommand = server.GetLaunchCommand()
            if not launchCommand:
                Logger.Warning(f"MCP[{server.name}]: missing launch command, skipped")
                continue

            client = McpStdioClient(server.name, launchCommand, server.ResolveEnv())
            started = await client.StartAsync(cancellationToken)
            if not started:
                continue
            self._clients.append(client)

            if not await client.InitializeAsync(cancellationToken):
                client.Terminate()
                continue

            discovered = await client.ListToolsAsync(cancellationToken)
            for spec in discovered:
                name = spec.get("name", "")
                if not name:
                    continue
                tools.append(McpTool(
                    client=client,
                    serverName=server.name,
                    remoteName=name,
                    description=spec.get("description", ""),
                    parameters=spec.get("inputSchema", {}),
                ))
            Logger.Info(f"MCP[{server.name}]: connected, {len(discovered)} tool(s) discovered")

        return tools

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
        return f"McpComponent(servers={len(self._servers)})"

    def __contains__(self, name: str) -> bool:
        return name in self._servers
