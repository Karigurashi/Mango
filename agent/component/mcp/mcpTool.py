"""McpTool —— 将 MCP Server 暴露的远程工具适配为框架内的 BaseTool。

每个 McpTool 持有一个 McpStdioClient 引用与远程工具名，ExecuteAsync 时
通过 client.CallToolAsync 转发调用，把结果包装为 ToolResult。
工具名以 ``mcp__{server}__{tool}`` 命名，避免与本地工具或跨 Server 冲突。
"""

from __future__ import annotations

from typing import Any

from agent.component.tool.baseTool import BaseTool
from agent.component.tool.eToolCategory import EToolCategory
from agent.component.tool.toolResult import ToolResult

from .mcpClient import McpStdioClient


class McpTool(BaseTool):
    """MCP 远程工具适配器。

    动态实例（非装饰器注册），由 McpComponent 在连接 Server 后创建并注入
    ToolComponent。name/description/parameters 来自 Server 的 tools/list。
    """

    category: EToolCategory = EToolCategory.CUSTOM
    timeout: float | None = 120.0

    def __init__(
        self,
        client: McpStdioClient,
        serverName: str,
        remoteName: str,
        description: str,
        parameters: dict[str, Any],
    ) -> None:
        self._client = client
        self._remoteName = remoteName
        self.name = f"mcp__{serverName}__{remoteName}"
        self.description = description or f"MCP tool '{remoteName}' from server '{serverName}'"
        self.parameters = parameters or {"type": "object", "properties": {}}

    async def _InvokeAsync(self, **kwargs) -> ToolResult:
        """转发调用到 MCP Server。

        参数为动态 schema，遵循 BaseTool 既有的 ExecuteAsync(**arguments) 约定。
        """
        success, content = await self._client.CallToolAsync(self._remoteName, dict(kwargs))
        if success:
            return ToolResult.Ok(content, toolName=self.name)
        return ToolResult.Fail(content, toolName=self.name)

    def __repr__(self) -> str:
        return f"McpTool(name={self.name!r})"
