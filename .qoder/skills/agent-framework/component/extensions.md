# 扩展系统

Rule、MCP、Memory 三类扩展，由 HarnessComponent 在 BuildAsync 阶段统一加载并注入 LOD0 或工具系统。

---

## Rule 规则引擎

把项目级约束/偏好/规范沉淀到 `.rule.md` 文件，按四种触发模式动态注入 LLM 上下文。与 Skill 互补：Rule 是"做事的边界"，Skill 是"做事的步骤"。

### 四种触发模式

| 模式 | 注入时机 |
|------|---------|
| ALWAYS_APPLY | 每次 Run 都注入 system（Harness LOD0 阶段合并） |
| GLOB_MATCH | 当前涉及文件路径匹配 `globs` 模式时注入 |
| DESCRIPTION_MATCH | 用户输入关键词命中 `description` 时注入 |
| MANUAL_INVOKE | 用户消息含 `@rule-name` 时注入 |

`.rule.md` 格式：YAML frontmatter（name/description/globs/alwaysApply）+ Markdown 正文。triggerMode 可从 frontmatter 推断。

### 关键设计

- `GetAlwaysApplyBody()` 拼接所有 ALWAYS_APPLY Rule 正文，用 `---` 分隔，由 Harness 注入 LOD0。
- GLOB_MATCH 的 globs 在加载时编译为 regex 缓存。
- MANUAL_INVOKE 不会被自动注入，必须显式 @name 引用。
- `_matchStats` 累计命中次数，用于观测。

---

## MCP Server 管理

把 Model Context Protocol 的远程工具适配为框架内本地工具。每个 MCP Server 通过 JSON-RPC 暴露 `tools/list` 和 `tools/call`，McpComponent 将远程工具包装为 McpTool（继承 BaseTool）注入 ToolComponent。

### 传输方式

- **STDIO**：本地子进程，换行分隔 JSON-RPC（已完整实现）
- HTTP/SSE：远程传输（预留，待实现）

### 工具注入流程

```
HarnessComponent.BuildAsync:
  LoadFromMCPJson(config.mcpJsonPath)        # 解析 .mcp.json
  ConnectAllAsync()                           # 顺序连接所有 enabled Server
    → Start → Initialize → tools/list
    → 每个工具包成 McpTool: mcp__{server}__{tool}
  RegisterTool(mcpTool)                       # 逐个注入 ToolComponent
  BindTools(GetAllToolSpecs())                # 统一绑给 LLM
```

### 关键设计

- **命名空间隔离**：`mcp__{server}__{tool}` 避免跨 Server 重名。
- **每 Server 独立子进程**，`_ioLock` 串行化 stdin/stdout。
- **stderr 持续 drain**：避免子进程阻塞。
- **断线重连**：CallToolAsync 失败 + 进程退出 → 自动 ReconnectAsync 一次。
- **单 Server 失败不阻塞其他**。
- **OnDestroy 同步 Terminate**：子进程不残留。

---

## Memory 跨会话记忆

长期记忆层：每个 Session 的摘要保存为不可变 Markdown，通过 INDEX.md 提供导航入口。上下文只放 INDEX（< 500 tokens），按需加载，做到信息与 token 解耦。

### 目录结构

```
<memoryDir>/
├── sessions/{sessionId}.md    # 不可变会话摘要
└── memory/
    ├── INDEX.md               # 导航索引（LOD0 注入入口）
    └── LOG.md                 # 追加式操作日志
```

### 关键设计

- **INDEX.md 是唯一入口**：Harness 调用 `LoadContextBlocks()` 返回 INDEX.md 全文注入 LOD0。
- **会话摘要不可变**：写入后只读不改。
- **LRU 裁剪**：sessions/ 超过 15 条时按 mtime 删除最旧 5 条。
- **原子写**：tempfile + os.replace，崩溃不留半文件。
- **MemoryIndex 只读**：不负责写入，索引由外部维护。
