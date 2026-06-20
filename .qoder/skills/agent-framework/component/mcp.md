# McpComponent MCP Server 管理

> 源码：[`agent/component/mcp/mcpComponent.py`](../../../agent/component/mcp/mcpComponent.py)、[`agent/component/mcp/mcpClient.py`](../../../agent/component/mcp/mcpClient.py)、[`agent/component/mcp/mcpServerConfig.py`](../../../agent/component/mcp/mcpServerConfig.py)、[`agent/component/mcp/mcpTool.py`](../../../agent/component/mcp/mcpTool.py)、[`agent/component/mcp/eMcpTransport.py`](../../../agent/component/mcp/eMcpTransport.py)

McpComponent 把 **Model Context Protocol** 的远程工具能力适配为框架内的本地工具：每个 MCP Server 通过 JSON-RPC 暴露一组 `tools/call`，McpComponent 启动时连接所有 Server、调用 `tools/list` 发现工具，把每个远程工具包成 `McpTool`（继承 `BaseTool`）注入 ToolComponent。LLM 看到的就是普通工具，无感知协议差异。

## 1 模块结构

```
agent/component/mcp/
├── mcpServerConfig.py   # 单 Server 静态配置（兼容 .mcp.json）
├── eMcpTransport.py     # STDIO / HTTP / SSE 传输枚举
├── mcpClient.py         # McpStdioClient（JSON-RPC over stdio）
├── mcpTool.py           # McpTool（BaseTool 子类，转发到 client）
└── mcpComponent.py      # 总管：注册 / 加载 / 连接 / 描述注入 / 销毁
```

## 2 EMcpTransport 三种传输

```text
EMcpTransport (Enum, str):
    STDIO = "stdio"   # 本地子进程，stdin/stdout JSON-RPC（最常用）
    HTTP  = "http"    # 远程 streamable HTTP（推荐用于远程）
    SSE   = "sse"     # Server-Sent Events（已废弃，向后兼容）
```

> 当前实现完整支持 **STDIO**；HTTP/SSE 已留出 `IsRemote` 接口位，待 `RemoteMcpClient` 落地。

## 3 McpServerConfig（mcpServerConfig.py）

```text
McpServerConfig:
  ├─ name        : str                  # 唯一标识
  ├─ transport   : EMcpTransport
  ├─ command/args: stdio 启动命令
  ├─ url         : http/sse 连接地址
  ├─ env         : dict[str, str]       # 支持 ${VAR} 占位符
  ├─ scope       : "local"|"project"|"user"  # 对标 Claude Code
  └─ enabled     : bool

工具方法：
  ToDict / FromDict      # .mcp.json 兼容
  GetLaunchCommand()     # → [command, *args]，非 stdio 返回 None
  ResolveEnv()           # 替换 ${VAR} 占位符为实际环境变量
  IsStdio / IsRemote
```

`.mcp.json` 兼容示例：

```json
{
  "mcpServers": {
    "filesystem": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "${WORKSPACE}"],
      "env": {"WORKSPACE": "${PWD}"}
    }
  }
}
```

## 4 McpStdioClient（mcpClient.py）

JSON-RPC 2.0 over newline-delimited stdio 客户端。

### 4.1 生命周期

```text
StartAsync ──► InitializeAsync ──► ListToolsAsync / CallToolAsync ──► Terminate

字段：
  _proc:        asyncio.subprocess.Process
  _stderrTask:  asyncio.Task                # 持续排空 stderr，避免管道阻塞
  _requestId:   int                          # 自增请求 id
  _ioLock:      asyncio.Lock                 # 串行化 stdin/stdout
  _initialized: bool

常量：
  _STREAM_LIMIT          = 16 MB              # 单行最大长度（大结果工具兼容）
  _PROTOCOL_VERSION      = "2024-11-05"
  _DEFAULT_READ_TIMEOUT  = 120 s              # 单请求读超时
```

### 4.2 关键方法

| 方法 | 行为 |
|------|------|
| `StartAsync` | `asyncio.create_subprocess_exec` 启动子进程，启动 stderr drain task |
| `InitializeAsync` | 发送 `initialize` 握手 + `notifications/initialized` 通知 |
| `ListToolsAsync` | `tools/list` → 返回 list[{name, description, inputSchema}] |
| `CallToolAsync` | `tools/call` 调用；**首次失败 + 进程已退出 → 自动 ReconnectAsync 一次重试** |
| `ReconnectAsync` | Terminate + Start + Initialize；任一步失败返回 False |
| `Terminate` | 同步 kill 子进程 + 取消 stderr task |
| `_RequestAsync` | 通用 JSON-RPC 请求：`_ioLock` 内串行化写入 + 按 id 配对响应（跳过通知） |

### 4.3 容错设计

```text
错误恢复链路：
  CallToolAsync(name, args)
    ├─ _CallToolOnceAsync 成功 ──► return True, content
    └─ 失败 + IsAlive == False
          └─ ReconnectAsync ──► 成功 ──► 再次 _CallToolOnceAsync
                            └─► 失败 ──► return False, "reconnect failed"
```

避免远端 MCP Server 偶尔崩溃后所有后续工具调用永久失败。

## 5 McpTool（mcpTool.py）

```text
class McpTool(BaseTool):
    category = EToolCategory.CUSTOM
    timeout  = 120.0

    __init__(client, serverName, remoteName, description, parameters):
        self._client     = client
        self._remoteName = remoteName
        self.name        = f"mcp__{serverName}__{remoteName}"   # 命名空间隔离
        self.description = description
        self.parameters  = parameters or {"type":"object","properties":{}}

    _InvokeAsync(**kwargs) -> ToolResult:
        success, content = await self._client.CallToolAsync(self._remoteName, kwargs)
        return ToolResult.Ok(content) if success else ToolResult.Fail(content)
```

* **命名空间**：`mcp__{server}__{tool}` 避免跨 Server 重名 / 与本地工具冲突；
* **schema 透传**：parameters 直接来自 Server 的 `tools/list` 响应，LLM 看到原生 JSON Schema。

## 6 McpComponent（mcpComponent.py）

### 6.1 字段

```text
McpComponent
  ├─ _servers:  dict[str, McpServerConfig]
  ├─ _clients:  dict[str, McpStdioClient]
  └─ _CONNECT_ALL_TIMEOUT = 60.0     # ConnectAllAsync 整体超时
```

### 6.2 关键方法

| 方法 | 行为 |
|------|------|
| `Register(config)` | 注册 Server（程序化或测试用）|
| `LoadFromMCPJson(path)` | 解析 `.mcp.json` 批量注册 |
| `ToMCPJson() -> str` | 反序列化（持久化场景）|
| `ConnectAllAsync` | **并行**启动所有 enabled 的 Server + Initialize + tools/list；整体 `wait_for(60s)` 保护；**单个 Server 失败仅记日志，不阻塞其他**；返回 list[McpTool] |
| `GetToolDescriptions() -> str` | 渲染 `<server name="X">tool description...</server>` 块，注入 LOD0 |
| `GetAllMcpTools() -> list[McpTool]` | 已发现的所有 McpTool（供 ToolComponent 注入） |
| `OnDestroy` | 同步 Terminate 所有 client（避免子进程泄漏） |

### 6.3 ConnectAllAsync 细节

```text
async def ConnectAllAsync():
    tasks = []
    for cfg in _servers.values():
        if not cfg.enabled or not cfg.IsStdio():
            continue
        client = McpStdioClient(cfg.name, cfg.GetLaunchCommand(), cfg.ResolveEnv())
        _clients[cfg.name] = client
        tasks.append(_ConnectOne(client))    # Start + Initialize + tools/list

    try:
        await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True),
                               timeout=_CONNECT_ALL_TIMEOUT)
    except asyncio.TimeoutError:
        Logger.Warning("MCP ConnectAll timeout, partial servers may be unavailable")

    # gather 中单个异常不抛出，仅在该 Server 的 _clients 项保持空工具列表
```

## 7 与其他组件的关系

```text
HarnessComponent.BuildAsync
  ├─ mcp.LoadFromMCPJson(config.mcpJsonPath)        # 在 _ReloadExtensions 阶段
  ├─ mcp.ConnectAllAsync()                          # IngestSystem 阶段
  ├─ blocks.append("<mcp_servers>" + mcp.GetToolDescriptions() + "</mcp_servers>")
  └─ for tool in mcp.GetAllMcpTools(): tools.AddTool(tool)

Agent._RunReActCoreAsync
  └─ tool_call: mcp__filesystem__read_file
       ──► ToolComponent.DispatchAsync
       ──► McpTool._InvokeAsync
       ──► McpStdioClient.CallToolAsync (JSON-RPC)
```

## 8 关键不变式

1. **每个 MCP Server 一个独立子进程**，由 `_ioLock` 串行化 stdin/stdout，避免并发请求错乱。
2. **请求/响应通过 `id` 配对**；中间出现的通知（无 id）被忽略，保证流上的"out-of-order"消息不会卡死调用方。
3. **stderr 持续 drain**：避免子进程因 stderr 缓冲写满而阻塞。
4. **单 Server 失败不影响其他 Server**：ConnectAll 用 `gather(return_exceptions=True)`。
5. **OnDestroy 强制同步 Terminate**：哪怕 Run 异常退出，子进程也不残留。
6. **远程传输 (HTTP/SSE) 暂未实现**：`IsRemote` Server 当前会被 ConnectAllAsync 跳过 + Logger.Warning。
