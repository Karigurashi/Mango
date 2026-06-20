# DataComponent 数据与配置

> 源码：[`agent/component/data/dataComponent.py`](../../../agent/component/data/dataComponent.py)、[`agent/component/data/agentConfig.py`](../../../agent/component/data/agentConfig.py)、[`agent/component/data/eAgentState.py`](../../../agent/component/data/eAgentState.py)

DataComponent 是整个 Agent 的**配置/状态/LLM 实例的唯一权威**，第一个挂载、最后一个销毁。任何其他组件需要"配置某项参数"或"读取/写入运行状态"时，都通过 `agent.GetComponent(DataComponent)` 反查，避免参数下钻造成的耦合。

## 1 模块结构

```
agent/component/data/
├── dataComponent.py    # 顶层组件：托管 config / state / llm
├── agentConfig.py      # 30+ 字段配置 dataclass + 校验 + 序列化
└── eAgentState.py      # EAgentState 枚举 + VALID_TRANSITIONS
```

## 2 DataComponent 职责（dataComponent.py）

```text
DataComponent
  ├─ _config: AgentConfig          # 启动后冻结的运行配置
  ├─ _llm:    BaseLLM              # LLM 实例（外部注入或工厂创建）
  └─ _state:  EAgentState          # 当前 Agent 状态（带状态机校验）
```

| 方法 | 功能 |
|------|------|
| `__init__(config, llm)` | **唯一接收业务参数的组件**——为了避免 LLM 实例化的复杂度被框架内部承担 |
| `OnInitialize` | 调用 `config.Validate()`，触发非法字段早失败 |
| `Config / Llm` | 只读 property，禁止运行时改写 |
| `State` setter | 校验目标状态是否在 `VALID_TRANSITIONS[current]` 内；非法转移仅 `Logger.Warning`，**不抛异常**——避免 ReAct 主循环因状态机末端 corner case 整个崩溃 |
| `OnDestroy` | 不主动销毁 LLM（外部生命周期），仅清空引用 |

## 3 AgentConfig（agentConfig.py）

`AgentConfig` 是带 `@dataclass` 的纯数据容器，按职责分四组（共 30+ 字段）。所有默认值都来自模块级私有常量 `_DEFAULT_TEMPLATE`。

### 3.1 字段分组

| 组 | 字段示例 | 角色 |
|----|---------|------|
| **ReAct 循环** | `maxIterations` / `maxRetries` / `retryBackoffBase` / `temperature` / `maxTokens` | 控制单次 Run 的迭代上限、重试退避、生成参数 |
| **上下文引擎** | `contextBudget` / `contextBudgetRatio` / `keepRecentTurns` / `lod3LineThreshold` / `lod3SizeThreshold` / `compactionPrompt` / `summaryMaxTokens` / `batchSummaryMaxTokens` | LOD 引擎/微压缩/压缩 LLM 调参 |
| **外存管理** | `contextStoreDir` / `contextStoreMaxFileSize` / `contextStoreMaxTotalSize` / `memoryDir` / `loggingDir` | 落盘根目录与容量水位 |
| **日志** | `logLevel` / `logFormat` / `logSampleRate` / `logFlushInterval` | LoggingComponent 行为开关 |

### 3.2 派生属性 `effectiveBudget`

```text
effectiveBudget = min(contextBudget, modelContextWindow * contextBudgetRatio)
```

* `contextBudget` 是用户硬限；
* `contextBudgetRatio` 是相对模型 context window 的安全比例（默认 0.85）；
* 取较小者，**保证既不超用户预算、也不超模型物理上限**。

### 3.3 序列化

| 方法 | 用途 |
|------|------|
| `FromDict(d) -> AgentConfig` | 从 JSON / 配置中心加载，缺失字段回退默认值 |
| `ToDict() -> dict` | 持久化到磁盘 / 上报观测 |
| `Default()` | 返回 `_DEFAULT_TEMPLATE` 的浅拷贝（用于"不指定就用默认"场景） |

### 3.4 启动校验 `Validate()`

```text
Validate(self)
  ├─ maxIterations ≤ 0           ──► raise ValueError
  ├─ contextBudget ≤ 0           ──► raise ValueError
  ├─ keepRecentTurns < 0         ──► raise ValueError
  ├─ contextBudgetRatio ∉ (0,1]  ──► raise ValueError
  ├─ logSampleRate ∉ [0, 1]      ──► raise ValueError
  └─ memoryDir / contextStoreDir 路径合法性
```

> 由 `DataComponent.OnInitialize` 主动调用，**配置错误在启动期立刻报错**，避免运行到第 N 轮才崩。

## 4 EAgentState 状态机（eAgentState.py）

```text
                      ┌────────────► WAITING_USER ──┐
                      │                              │
        IDLE ──► THINKING ──► ACTING ──► THINKING …  │
                      │           │                  │
                      ▼           ▼                  │
                  FINISHED ◄──────┘ ◄───────────────┘
                      │
                      ▼
                    ERROR
```

### 4.1 枚举值

| 值 | 含义 |
|----|------|
| `IDLE` | 初始 / 上次 Run 结束后 |
| `THINKING` | 正在调 LLM |
| `ACTING` | 正在执行工具 |
| `WAITING_USER` | 阻塞等待用户额外输入（可选模式） |
| `FINISHED` | 单次 Run 正常终止 |
| `ERROR` | Run 因不可恢复异常终止 |

### 4.2 VALID_TRANSITIONS

`EAgentState.VALID_TRANSITIONS: Dict[EAgentState, Set[EAgentState]]` 是合法迁移表：

```text
IDLE          → {THINKING, ERROR}
THINKING      → {ACTING, FINISHED, WAITING_USER, ERROR}
ACTING        → {THINKING, FINISHED, ERROR}
WAITING_USER  → {THINKING, FINISHED, ERROR}
FINISHED      → {IDLE}                # 允许 IDLE 重启下一轮 Run
ERROR         → {IDLE}                # 同上，恢复型重启
```

> 非法迁移 **不会抛异常**，只在 `Logger.Warning` 留痕——这是有意为之的妥协：状态机过严会让上层每次都包 `try/except`，污染主循环；过宽则失去观测价值，故选择"记录但不阻断"。

## 5 与其他组件的交互

| 调用方 | 通过 DataComponent 获取 |
|--------|------------------------|
| `LLMComponent.OnInitialize` | `_llm`（绑定 requestParams） |
| `ContextComponent.OnInitialize` | `_config`（构造 LOD 阈值） + `_llm`（压缩用 LLM） |
| `MemoryComponent.OnInitialize` | `_config.memoryDir` |
| `LoggingComponent.OnInitialize` | `_config.loggingDir / logLevel / logFormat` |
| `Agent._RunReActCoreAsync` | `_state` 状态机迁移 |

## 6 关键不变式

1. **配置在 `OnInitialize` 后视为冻结**——所有组件持有的是 `AgentConfig` 引用，运行时改字段会破坏可重入性，框架不做防御性深拷贝，但通过约定禁止改写。
2. **状态机宽容**：非法状态迁移不抛异常，仅记录；保证 ReAct 主循环不被状态机问题打断。
3. **LLM 单实例**：整个 Agent 生命周期内只持有一个 `BaseLLM`，跨组件共享同一对象，避免重复鉴权和连接池开销。
