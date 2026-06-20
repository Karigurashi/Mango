# ToolComponent 工具系统

> 源码：[`agent/component/tool/toolComponent.py`](../../../agent/component/tool/toolComponent.py)、[`agent/component/tool/baseTool.py`](../../../agent/component/tool/baseTool.py)、[`agent/component/tool/eToolCategory.py`](../../../agent/component/tool/eToolCategory.py)、[`agent/component/tool/toolResult.py`](../../../agent/component/tool/toolResult.py)

ToolComponent 是 Agent 与"行动能力"之间的总线。它统一了**工具注册（装饰器）+ 工具发现（spec 注入 LLM）+ 工具调度（DispatchAsync）+ 执行统计**四件事，所有内置工具、Skill 加载工具、MCP 远程工具最终都汇集到这里，由 ReAct 主循环以同一接口调用。

## 1 模块结构

```
agent/component/tool/
├── toolComponent.py        # 总线：注册 / 发现 / 调度 / 统计
├── baseTool.py             # BaseTool 抽象基类（双轨执行）
├── eToolCategory.py        # 工具分类枚举
├── toolResult.py           # ToolResult 不可变结果
├── control/                # 内置：流程控制（todoWrite）
├── file/                   # 内置：read/write/list/grep/search/delete
├── network/                # 内置：fetchContent / searchWeb
└── shell/                  # 内置：bash
```

## 2 BaseTool 抽象（baseTool.py）

每个工具是 `BaseTool` 的子类，类属性即元信息，实例方法实现执行逻辑。

### 2.1 类属性（声明即注册元信息）

| 属性 | 类型 | 作用 |
|------|------|------|
| `name` | `str` | 工具名（function calling 唯一标识） |
| `description` | `str` | 给 LLM 看的语义说明 |
| `parameters` | `dict` | JSON Schema，LLM 据此构造调用参数 |
| `category` | `EToolCategory` | 分类（FILE/SHELL/NETWORK/...） |
| `timeout` | `float \| None` | 单次执行超时，覆盖 ToolComponent 类级 / 实例级默认 |
| `resultLodLevel` | `EContextLodLevel` | 结果默认 LOD 等级（LOD2 可丢弃 / LOD1 可摘要） |
| `skipPersist` | `bool` | 结果是否跳过 PersistToolResult 落盘判定（默认 False）|

### 2.2 双轨执行

```text
ExecuteAsync(**kwargs) -> ToolResult       # 框架统一入口
  │
  ├─ 子类 override _InvokeAsync ──► 直接 await
  └─ 子类只 override _Invoke   ──► run_in_executor 包同步逻辑
```

* `_Invoke(**kwargs)`：同步 IO/计算工具直接重写这个方法；
* `_InvokeAsync(**kwargs)`：异步 IO（aiohttp / asyncpg）重写这个方法；
* **MUST 二选一**，子类同时实现两个时优先 `_InvokeAsync`。

### 2.3 工具方法

| 方法 | 功能 |
|------|------|
| `ToToolSpec() -> dict` | 输出 OpenAI function calling 格式的 spec，供 `LLMComponent.BindTools` |
| `_SanitizePath(path)` | 通用路径安全：禁止 `..` 越级、Windows 反斜杠归一化 |

## 3 EToolCategory 分类（eToolCategory.py）

```text
FILE        — read / write / list / grep / search / delete
SHELL       — bash / 脚本执行
NETWORK     — http fetch / web search
KNOWLEDGE   — 知识库查询、向量检索
AGENT       — 子 Agent 调用（嵌套 Agent）
MCP         — MCP Server 暴露的远程工具（McpTool）
CUSTOM      — 用户自定义
```

> 分类用于：观测分组、日志标签、批量启用/禁用（如生产环境禁用 SHELL）。

## 4 ToolResult（toolResult.py）

```text
ToolResult(NamedTuple):
  ├─ success:  bool
  ├─ content:  str              # 注入 LLM 的文本
  ├─ data:     Any              # 程序可消费的结构化数据
  ├─ error:    str              # success=False 时填写
  └─ toolName: str

  快捷工厂：
    ToolResult.Ok(content, data=None, toolName="")
    ToolResult.Fail(error, toolName="")

  方法：
    ToLLMContent() -> str       # 成功 → content；失败 → "Error (toolName): error"
    WithToolName(name)          # 不可变替换 toolName
```

> 用 NamedTuple 保证不可变；事件流追加场景（流式 UI / 日志）零深拷贝开销。

## 5 ToolComponent 总线（toolComponent.py）

### 5.1 字段

| 字段 | 作用域 | 说明 |
|------|--------|------|
| `_toolClasses: dict[str, Type[BaseTool]]` | **类级共享** | `@Register` 装饰器写入，进程级单例 |
| `_tools: dict[str, BaseTool]` | **实例级隔离** | 当前 Agent 拥有的工具实例，与其他 Agent 不互通 |
| `_defaultTimeout: float = 300.0` | 实例级 | 单工具未声明 `timeout` 时的兜底 |
| `_executionStats: deque(maxlen=100)` | 实例级 | 最近 100 次执行的耗时/结果，用于观测 |

### 5.2 `@Register` 装饰器

```text
@ToolComponent.Register
class ReadFileTool(BaseTool):
    name = "read_file"
    ...
```

* 装饰器把类写入 `ToolComponent._toolClasses[name]`；
* 仅注册"类"，**不实例化**——实例化推迟到当前 Agent 真正需要时；
* **进程内幂等**：重复 import 同一工具不会重复注册（按 name 去重并 Logger.Warning）。

### 5.3 `LoadBuiltins()` 触发器

```text
LoadBuiltins(self):
    # 仅 import 触发装饰器；不实例化
    import agent.component.tool.control     # → todoWriteTool
    import agent.component.tool.file        # → read/write/list/grep/search/delete
    import agent.component.tool.network     # → fetchContent / searchWeb
    import agent.component.tool.shell       # → bash
    self._InstantiateAll()                  # 把 _toolClasses 中所有类实例化到 _tools
```

* 由 HarnessComponent.BuildAsync 调用；
* **幂等**：第二次调用只补齐尚未实例化的工具。

### 5.4 调度 `DispatchAsync`

```text
DispatchAsync(name: str, args: dict, cancellationToken=None) -> ToolResult
  │
  ├─ tool = self._tools.get(name)
  │     └─ 不存在 ──► return ToolResult.Fail(f"Unknown tool: {name}")
  │
  ├─ timeout = tool.timeout                      # 优先级 1：实例属性
  │           or self._defaultTimeout            # 优先级 3：类级默认 300s
  │
  ├─ try:
  │     result = await asyncio.wait_for(
  │         tool.ExecuteAsync(**args),
  │         timeout=timeout,
  │     )
  │   except asyncio.TimeoutError ──► ToolResult.Fail(f"Tool {name} timed out after {timeout}s")
  │   except Exception as exc       ──► ToolResult.Fail(f"Tool {name} failed: {exc}")
  │
  └─ self._RecordStats(name, duration, success)  # 写入 _executionStats deque
     return result.WithToolName(name)
```

### 5.5 内置工具清单

| 分类 | 工具 | 说明 |
|------|------|------|
| FILE | `read_file` | 读文件（支持行范围） |
| FILE | `write_file` | 原子写入（tempfile + os.replace） |
| FILE | `list_dir` | 列目录 |
| FILE | `grep_code` | ripgrep 风格全文检索 |
| FILE | `search_file` | 按 glob 找文件 |
| FILE | `delete_file` | 安全删除（白名单根目录） |
| SHELL | `bash` | shell 命令执行（含 cwd / timeout / env） |
| NETWORK | `fetch_content` | HTTP GET / 网页提取 |
| NETWORK | `search_web` | 搜索引擎查询 |
| CONTROL | `todo_write` | 任务清单写入（流程控制） |

> Skill 系统会注入额外的 `load_skill`（见 [skill.md](skill.md)），MCP 系统会动态注入 `mcp__{server}__{tool}`（见 [mcp.md](mcp.md)）。

## 6 与其他组件的关系

```text
HarnessComponent.BuildAsync
   │  ToolComponent.LoadBuiltins()                # 装载内置
   │  SkillComponent.GetToolDefinition()          # 注册 load_skill
   │  McpComponent.ConnectAllAsync()              # 发现 + 注入 McpTool
   └► LLMComponent.BindTools(self.GetAllSpecs())  # 把所有工具一次性绑给 LLM

Agent._RunReActCoreAsync
   └─ tool_call ──► ToolComponent.DispatchAsync(name, args)
                         │
                         └─► Session.Append(TOOL result)
                            ContextComponent.PersistToolResult(if oversize)
```

## 7 关键不变式

1. **类级共享 / 实例级隔离**：`_toolClasses` 全进程一份，`_tools` 每 Agent 一份；保证装饰器只写一次，运行时各自独立。
2. **超时优先级**：`tool.timeout`（实例属性，可被工具自身覆盖） > `self._defaultTimeout`（实例级 300s 兜底）。
3. **任意异常**都被包装为 `ToolResult.Fail`，**不会抛出 ReAct 主循环**——主循环可专注于 LLM 决策，不必处理工具异常细节。
4. **执行统计 deque(maxlen=100)** 自动丢弃最旧记录，防止长 Run 内存膨胀。
5. **CancellationToken 透传**：用户中止 Run 时，正在跑的工具能在下一个 await 点感知并退出。
