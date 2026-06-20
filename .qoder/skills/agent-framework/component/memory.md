# MemoryComponent 跨会话记忆

> 源码：[`agent/component/memory/memoryComponent.py`](../../../agent/component/memory/memoryComponent.py)、[`agent/component/memory/memoryStore.py`](../../../agent/component/memory/memoryStore.py)、[`agent/component/memory/memoryIndex.py`](../../../agent/component/memory/memoryIndex.py)、[`agent/component/memory/memoryCompiler.py`](../../../agent/component/memory/memoryCompiler.py)、[`agent/component/memory/checkpointManager.py`](../../../agent/component/memory/checkpointManager.py)、[`agent/component/memory/eMemoryCategory.py`](../../../agent/component/memory/eMemoryCategory.py)

MemoryComponent 是 Brain Agent 的**长期记忆层**，对标 Karpathy 在 "LLM Wiki" 中提出的"可编译知识库"思想：把每个 Session 的摘要保存为不可变 Markdown，再由 LLM 编译为分类化的"记忆页面"，最后通过 INDEX.md 提供导航——上下文里只放 INDEX，按需加载具体页面，做到**信息与 token 解耦**。

## 1 模块结构

```
agent/component/memory/
├── memoryComponent.py     # 顶层组件：编排 store / index / compiler / lint
├── memoryStore.py         # 文件 I/O 层（原子写、frontmatter、LRU 裁剪）
├── memoryIndex.py         # INDEX.md 导航
├── memoryCompiler.py      # LLM 驱动的摘要 → 记忆页面编译
├── memoryLint.py          # 记忆质量检测
├── checkpointManager.py   # 工作流断点
└── eMemoryCategory.py     # PREFERENCE / DECISION / PATTERN / REFERENCE
```

## 2 目录结构

```text
<memoryDir>/
├── sessions/                    # 不可变会话摘要
│   ├── {sessionId}.md           # 由 SessionComponent.SaveToMemory 写入
│   └── ...
├── memory/                      # LLM 编译产出
│   ├── INDEX.md                 # 导航："## Preferences" / "- [[page]] - desc"
│   ├── LOG.md                   # 追加式编译日志
│   ├── preferences/             # 用户偏好
│   ├── decisions/               # 架构决策
│   ├── patterns/                # 反馈模式
│   └── references/              # 外部引用
└── checkpoints/                 # 工作流断点
    └── {workflowName}/
        ├── {sessionId}.md
        └── latest.md
```

## 3 EMemoryCategory（eMemoryCategory.py）

```text
EMemoryCategory(str, Enum):
    PREFERENCE = "preferences"   # 偏好：编码风格、命名习惯、工具选择
    DECISION   = "decisions"     # 决策：技术选型、设计取舍
    PATTERN    = "patterns"      # 模式：纠错规则、确认的正确做法
    REFERENCE  = "references"    # 引用：API 文档、看板、联系人
```

* 枚举值即磁盘子目录名，`FromDirName` 兼容单复数（"preference"/"preferences"）。
* `DirName` / `Label`（中文）便于 INDEX 渲染与日志输出。

## 4 MemoryStore（memoryStore.py）

纯文件 I/O，不依赖 LLM。

| 方法 | 行为 |
|------|------|
| `_InitDirs` | 启动时确保所有子目录存在 |
| `ParseFrontmatter / BuildFrontmatter` | YAML frontmatter 工具方法 |
| `WriteFile` | **原子写**：tempfile + os.replace，崩溃不留半文件 |
| `AppendFile` | 追加（用于 LOG.md） |
| `SaveSession` | 写入 `sessions/{id}.md` 后调用 `_PruneSessions` |
| `_PruneSessions(MAX_SESSIONS=15, PRUNE_COUNT=5)` | 超过 15 个会话时按 mtime 删除最旧的 5 个 |
| `SaveMemoryPage / LoadMemoryPage / DeleteMemoryPage` | 记忆页面读写 |
| `AppendLog / ReadLog` | LOG.md 操作 |

> **LRU 裁剪 + 原子写 + frontmatter** 三件事是 Memory 持久化层的全部承诺；其他高层语义（编译、索引、检查）在上层模块。

## 5 MemoryIndex（memoryIndex.py）

INDEX.md 是 Memory 系统的**唯一入口**。`ContextAssembler` 只加载 INDEX.md（< 500 tokens），LLM 凭它决定是否进一步读具体页面。

```text
MemoryIndex
  ├─ _entries: dict[pageName, (EMemoryCategory, description)]
  ├─ Upsert(pageName, category, description)    # 增/改 + Save
  ├─ Remove(pageName)
  ├─ Find / GetAll
  ├─ _Load() / _Save()                          # 与 INDEX.md 同步
  └─ ToContextBlocks() -> list[str]             # LOD0 注入用，按分类分组
```

INDEX.md 格式：

```markdown
# Memory Index

## Preferences
- [[preferences-coding-style]] - Python coding style guide

## Decisions
- [[decisions-redis-cache]] - Redis caching strategy
```

## 6 MemoryCompiler（memoryCompiler.py）

LLM 驱动的"会话摘要 → 结构化记忆页面"编译器。

```text
CompileAsync(sessionIds=None) -> list[str]:
    sessions = self._LoadSessions(sessionIds or store.ListSessions())
    existing = self._BuildExistingPagesContext()  # 给 LLM 看的现有页面摘要
    if hasLLM:
        out = await llm.InvokeAsync([System(_COMPILE_SYSTEM_PROMPT),
                                      User(existing + sessions)])
        newPages = self._ParseCompileResult(out)
    else:
        newPages = self._CompileFallback(sessions)   # 直接存为 reference
    store.AppendLog(f"Compiled N sessions → M pages: ...")
    return newPages
```

### 6.1 编译 Prompt 关键约束

* 四类记忆 (PREFERENCE/DECISION/PATTERN/REFERENCE) 各自的提取规则；
* **跳过**："可从代码读到的（路径、结构）"、"调试解决方案"、"已文档化的内容"；
* **合并**：同主题已存在则更新而非新建；
* **NOOP**：无可记则输出 `---NOOP---`。

### 6.2 输出格式

```text
---PAGE---
category: preference
page_name: coding-style
title: Python Coding Style
confidence: high
sources: session-1, session-2
---BODY---
<Markdown 正文，含 **Why** / **How to apply** 子节>
---END---
```

`_ParseCompileResult` 按上述格式切块，写入对应 `memory/{category}/{pageName}.md` 并 `index.Upsert`。

## 7 CheckpointManager（checkpointManager.py）

工作流断点存档：把 WorkflowContext 的执行进度写为 Markdown，断电后可恢复。

| 方法 | 行为 |
|------|------|
| `Save(workflow, sessionId, completedNodes, currentNode, executionRound, contextData, nodeDetails)` | 写入 `checkpoints/{workflow}/{sessionId}.md` 同时更新 `latest.md` |
| `LoadLatest(workflow)` | 读 `latest.md` |
| `LoadBySession` | 按 sessionId |
| `ListCheckpoints / DeleteCheckpoint / ClearAll` | 管理 |
| `_ParseCheckpoint` | 解析 frontmatter → completedNodes/currentNode/executionRound/rawMeta |

> Checkpoint 是 **可选** 能力，由 WorkflowContext（更上层的工作流引擎）调用，与 ReAct 主循环无强耦合。

## 8 MemoryComponent（memoryComponent.py）

### 8.1 字段

```text
MemoryComponent
  ├─ _store:    MemoryStore
  ├─ _index:    MemoryIndex
  ├─ _compiler: MemoryCompiler
  └─ _lint:     MemoryLint
```

### 8.2 OnInitialize

```text
OnInitialize(agent):
    data = agent.GetComponent(DataComponent)
    self._store    = MemoryStore(baseDir=data.Config.memoryDir)
    self._index    = MemoryIndex(self._store)
    self._compiler = MemoryCompiler(self._store, self._index, llmClient=None)
    self._lint     = MemoryLint(self._store, self._index)
    self._TryInjectLLM(agent)               # 尝试拿 LLMComponent 给 compiler 用
```

### 8.3 主要方法

| 方法 | 行为 |
|------|------|
| `SaveSessionSummary(sessionId, content)` | 写入 `sessions/{id}.md`，触发 LRU 裁剪 |
| `SaveContextBlocks(name, blocks)` | 把 LOD0 块批量写入指定页面 |
| `LoadContextBlocks() -> list[str]` | **Harness 用**：读 INDEX.md 渲染为 LOD0 块（按分类分组）|
| `LoadSession(id) / LoadMemoryPage(category, name)` | 按需读取 |
| `FindMemoryPages(keyword)` | 简单关键词检索 |
| `CompileAsync(sessionIds=None)` | 触发 LLM 编译（手动或定时调用） |
| `LintAsync()` | 检测重复 / 过时 / 冲突的记忆页面 |

## 9 与其他组件的关系

```text
Agent 启动：
  HarnessComponent.BuildAsync
    └─ memory.LoadContextBlocks() ──► LOD0 注入 INDEX

Run 期间：
  Session.SaveToMemory ──► memory.SaveSessionSummary
                            └─► sessions/{sessionId}.md

后台 / 定期：
  memory.CompileAsync()  ──► sessions/* + INDEX → memory/{category}/*.md
                            ──► INDEX.md 更新

工作流：
  WorkflowContext ──► CheckpointManager.Save / LoadLatest
```

## 10 关键不变式

1. **会话摘要不可变**：写入 `sessions/{id}.md` 后只读不改；编译产物在 `memory/`，可被覆盖。
2. **INDEX.md 是唯一入口**：上下文里**永远不直接注入** memory/* 全文，避免占用 budget。
3. **原子写 + LRU**：保证崩溃不留半文件；保证 sessions/ 目录不会无限膨胀（默认 ≤ 15 条）。
4. **LLM 缺失时退化**：`MemoryCompiler.HasLLM=False` 时 `_CompileFallback` 直接把 session 内容存为 reference 页面，不至于丢数据。
5. **OnInitialize 时 LLM 可能尚未就绪**：`_TryInjectLLM` 容忍延迟绑定，首次 `CompileAsync` 时才真正调用 LLM。
