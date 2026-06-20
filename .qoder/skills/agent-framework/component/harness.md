# HarnessComponent 线束组件

> 源码：[`agent/component/harness/harnessComponent.py`](../../../agent/component/harness/harnessComponent.py)

HarnessComponent 是 Agent 启动时的**装配总管**：把内置工具、外部扩展（Rules / Skills / MCP）以及 LOD0 注入消息（Memory INDEX、规则正文、Skill 前缀、MCP 描述、环境快照）一次性"束"到一起。它对标汽车的"线束"——所有线缆从主机延伸到各部件的最后一公里都在这里收口。

## 1 职责

```
HarnessComponent
  ├─ BuildAsync          # 幂等装载入口，整个 Run 启动前调用
  ├─ _ReloadExtensions   # 加载 Rules / Skills / MCP（可选 reload 模式）
  ├─ LoadBuiltins        # 通过 ToolComponent 装入内置工具
  ├─ IngestSystem        # 多层 LOD0 消息注入到 Session
  └─ BindTools           # 把汇总的工具 spec 绑给 LLMComponent
```

## 2 BuildAsync 幂等装载

```text
BuildAsync(reloadExtensions: bool = True) -> None:
    if self._built and not reloadExtensions:
        return                                # 幂等：默认场景重复调用直接返回

    self._built = False
    if reloadExtensions:
        await self._ReloadExtensions()        # 见 §3
    self.tools.LoadBuiltins()                 # 触发 @Register 装饰器 + 实例化
    await self._IngestSystemAsync()           # 见 §4
    self.llm.BindTools(self.tools.GetAllSpecs())   # 一次性绑工具
    self._built = True
```

`_built` 标志保证：

* 默认 `reloadExtensions=True` 时，**每次 `BuildAsync` 都会重读磁盘扩展**，方便热更 Skill / Rule；
* 通过显式传 `reloadExtensions=False` 可在测试中复用已构建状态。

## 3 `_ReloadExtensions` 加载序列

```text
_ReloadExtensions():
    ├─ rule.LoadFromDirectory(config.ruleDir)         # 扫描 .rule.md
    ├─ skill.LoadFromDirectory(config.skillDir)       # 扫描 SKILL.md
    └─ if mcp:
         mcp.LoadFromMCPJson(config.mcpJsonPath)      # 解析 .mcp.json
```

> 注意：`McpComponent.ConnectAllAsync` **不在这里调用**，留到 §4 IngestSystem 阶段，因为连接 MCP Server 是 IO 异步操作，与 LOD0 注入合并执行更高效。

## 4 LOD0 注入管道（`_IngestSystemAsync`）

LOD0 = `RESIDENT`，永不压缩。Harness 以**多层叠加**方式注入到 Session 头部，构成模型每轮都看到的 system context。

```text
_IngestSystemAsync():
    blocks: list[str] = []

    ┌─ 1) Memory INDEX 注入 ─────────────────────┐
    │   if memory:
    │       blocks += memory.LoadContextBlocks()  # INDEX.md 解析的分类块
    └────────────────────────────────────────────┘

    ┌─ 2) Always-Apply Rules ────────────────────┐
    │   blocks.append(rule.GetAlwaysApplyBody())  # 多个 Rule 拼接
    └────────────────────────────────────────────┘

    ┌─ 3) Skill 前缀清单（Layer 1） ──────────────┐
    │   blocks.append(<available_skills>          │
    │                  + skill.GetAllPrefixes()   # ~100 tokens/Skill
    │                  + </available_skills>)     │
    │   self.tools.AddTool(skill.GetTool())       # 注入 load_skill 工具
    └────────────────────────────────────────────┘

    ┌─ 4) MCP 描述 + 工具发现 ───────────────────┐
    │   if mcp:
    │       await mcp.ConnectAllAsync()           # 启动子进程 + tools/list
    │       blocks.append(<mcp_servers>           │
    │                       + mcp.GetToolDescriptions()
    │                       + </mcp_servers>)     │
    │       for mcpTool in mcp.GetAllMcpTools():  │
    │           self.tools.AddTool(mcpTool)       # 注入 mcp__{server}__{tool}
    └────────────────────────────────────────────┘

    ┌─ 5) 环境快照 ──────────────────────────────┐
    │   blocks.append(self._BuildEnvironmentSnapshot())
    │       # OS / Python / cwd / 项目根 / git 简要 / 时间戳
    └────────────────────────────────────────────┘

    # 6) 每个 block 包装为 LOD0 消息逐条 Append
    for block in blocks:
        self.session.Append(ContextMessage.Create(
            chatMessage = ChatMessage.System(block),
            lodLevel    = EContextLodLevel.RESIDENT,
            turnIndex   = 0,
        ))
```

### 4.1 `_BuildEnvironmentSnapshot`

固定模板包含：

| 项 | 来源 |
|----|------|
| OS / 内核版本 | `platform.system()` / `platform.release()` |
| Python 版本 | `platform.python_version()` |
| Workspace 根 | `os.getcwd()` |
| 项目根 | `_DetectProjectRoot()`（递归找 `.git` / `pyproject.toml`） |
| Git 简要 | `git rev-parse --short HEAD`（失败时省略） |
| 时间戳 | `time.strftime("%Y-%m-%d %H:%M:%S %Z")` |

> 环境快照让 LLM 在每轮都掌握"我现在在哪台机器、哪个项目、哪条分支"，避免误用平台无关的命令。

## 5 BindTools 收口

```text
BindTools 调用时机（顺序）：
    LoadBuiltins         ──► tools._toolClasses 全部实例化
    Skill.GetTool        ──► load_skill 实例加入 _tools
    Mcp.ConnectAllAsync  ──► mcp__... 实例加入 _tools
    ─────────────────────
    LLMComponent.BindTools(tools.GetAllSpecs())   # 一次性聚合
```

只调一次 `BindTools`，之后整个 Run 期间 LLM 看到的工具列表稳定。**Skill 加载产生的"扩展上下文"是消息，不是工具**——不需要重绑工具。

## 6 与其他组件的关系

| 组件 | Harness 何时使用 |
|------|----------------|
| RuleComponent | `LoadFromDirectory` + `GetAlwaysApplyBody` |
| SkillComponent | `LoadFromDirectory` + `GetAllPrefixes` + `GetTool` |
| McpComponent | `LoadFromMCPJson` + `ConnectAllAsync` + `GetToolDescriptions` + `GetAllMcpTools` |
| ToolComponent | `LoadBuiltins` + `AddTool` + `GetAllSpecs` |
| MemoryComponent | `LoadContextBlocks` |
| SessionComponent | `Append`（每个 LOD0 block 一条 system 消息） |
| LLMComponent | `BindTools` |

## 7 关键不变式

1. **每个 Run 开始前 `BuildAsync` 必然被调用**（由 Agent 在 ReAct 循环外部触发）。
2. **`_built` 提供幂等保护**：默认情况下重复 BuildAsync 会重新加载扩展（热更友好），传 `reloadExtensions=False` 时直接 return。
3. **LOD0 注入顺序固定**：Memory → Rule → Skill → MCP → 环境快照——决定模型每轮 system 块的相对位置稳定。
4. **`BindTools` 一次绑齐**：避免运行时反复改写 `_requestParams.tools`，简化 LLM Provider 端的缓存策略。
