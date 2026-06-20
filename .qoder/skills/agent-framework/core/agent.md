# Agent 实现层

> 源码：[`agent/agent.py`](../../../agent/agent.py)、[`agent/simpleAgent.py`](../../../agent/simpleAgent.py)、[`agent/agentStreamEvent.py`](../../../agent/agentStreamEvent.py)

Agent 实现层是把 Core 容器、各 Component 与 LLM 协议串成一台可执行 Agent 的**编排器**。它本身不封装任何业务规则，只负责：组件挂载、四维调用入口、ReAct 主循环、流事件分发、并发与重试兜底。

## 1 类清单

```
agent/
├── agent.py             # Agent —— 完整 ReAct 编排器（591 行）
├── simpleAgent.py       # SimpleAgent —— 纯对话精简版（无 ReAct，65 行）
└── agentStreamEvent.py  # AgentStreamEvent / EAgentStreamEventType
```

## 2 Agent 构造与组件挂载（agent.py）

`Agent.__init__(config: AgentConfig)` 严格按依赖顺序挂载所有 Component。**顺序不可调换**，否则后挂载的组件 `OnInitialize` 会拿不到兄弟。

```text
Agent(config)
  └─ 顺序挂载（编号即 OnInitialize 顺序）：
       1  DataComponent      —— 配置/状态/LLM 对象的唯一持有者
       2  LLMComponent       —— 从 1 拉 llm，绑定 requestParams
       3  SessionComponent   —— 持有消息账本，OnInitialize 注入 Memory
       4  ContextComponent   —— 从 1/2/3 拉 config/llm/session，初始化 LOD/Lock
       5  RuleComponent      —— 加载 .rule.md
       6  SkillComponent     —— 加载 SKILL.md
       7  McpComponent       —— 注册 Server，但延迟到 Harness 才连接
       8  ToolComponent      —— 实例级 _tools；@Register 仅注册到类级 _toolClasses
       9  HarnessComponent   —— 装载工具/扩展、注入 LOD0
      10  LoggingComponent   —— 启动后台刷盘 Task
       └─ self.InitAllComponents()    # Core 层统一触发 OnInitialize
       └─ self._runLock = asyncio.Lock()  # 并发互斥
```

## 3 四维调用入口

LLM 调用有 **同步/异步 × 单次/流式** 两组维度，Agent 把这四种形态全部暴露成对偶 API，业务方根据调用栈环境（FastAPI / Jupyter / 测试 / CLI）自由选择。

| 维度 | 异步 | 同步桥接 |
|------|------|----------|
| 单次（返回最终文本） | `RunInvokeAsync(query) -> str` | `RunInvoke(query) -> str` |
| 流式（逐 token 增量） | `RunAsync(query) -> AsyncIterator[Event]` | `RunStream(query) -> Iterator[Event]` |

### 3.1 同步桥接策略

```text
RunInvoke / RunStream
  ├─ 检测当前线程是否已存在 running event loop
  │     ├─ 无 ──► asyncio.run(coro)   # 简单场景
  │     └─ 有 ──► 抛 RuntimeError，提示用户改用 *Async 版本（避免嵌套 loop 死锁）
```

### 3.2 异步入口流程

```text
RunInvokeAsync / RunAsync(query)
  ├─ _TryAcquireRunLock          —— 单实例并发互斥（见 §5）
  ├─ RunWithLifecycleAsync
  │     ├─ LoggingComponent.LogRunStart
  │     ├─ Session.Append(USER query)        —— ContextComponent.Ingest
  │     ├─ _RunReActCoreAsync 主循环（见 §4）
  │     ├─ Context.AfterTurnAsync           —— Cleanup / PurgeCompacted / SaveToMemory
  │     └─ LoggingComponent.LogRunEnd
  └─ finally: 释放 _runLock
```

`RunAsync` 与 `RunInvokeAsync` 共享同一主循环，区别仅在于：

* `RunAsync` 在循环内 **逐 chunk yield** `AgentStreamEvent`；
* `RunInvokeAsync` 不暴露事件，最终 return 拼接的最终文本。

## 4 ReAct 核心循环 `_RunReActCoreAsync`

```text
While turn < maxIterations:
    ┌─ THINK ──────────────────────────────────────────────┐
    │  Context.AssembleAsync ──► messages（含工具结果）       │
    │  LLM.StreamAsync(messages) → token deltas / tool_call  │
    │  EAgentState = THINKING                               │
    └───────────────────────────────────────────────────────┘
            │
            ├─ 模型仅返回文本 ──► EAgentState = FINISHED ──► break
            │
    ┌─ ACT ────────────────────────────────────────────────┐
    │  EAgentState = ACTING                                │
    │  for each tool_call:                                  │
    │      ToolComponent.DispatchAsync(name, args)          │
    │      Session.Append(TOOL result)                      │
    │      Context.PersistToolResult(if oversize)           │
    └───────────────────────────────────────────────────────┘
            │
    ┌─ OBSERVE ────────────────────────────────────────────┐
    │  Context.AfterTurnAsync(perTurn cleanup)              │
    │  Logging.LogToolExecution / LogStateChange            │
    └───────────────────────────────────────────────────────┘
turn += 1
```

> 详细时序见 [flows.md](flows.md)；本文档只列控制流框架。

### 4.1 重试与降级

| 机制 | 触发条件 | 行为 |
|------|---------|------|
| `_CallWithRetryAsync` | LLM 调用抛 `_IsRetryable` 类异常 | 指数退避重试 `maxRetries` 次（默认 3）|
| `_SanitizeToolMessages` | 重试前 | 剥离不完整的 tool_call / tool_result，保证消息序列对偶 |
| `_IsRetryable(exc)` | 判别 | 网络/超时/5xx → True；4xx/Schema 错误 → False |
| Iter 上限保护 | `turn >= maxIterations` | 强制结束，state = FINISHED，记录 warning |

## 5 并发安全 `_runLock`

```text
self._runLock: asyncio.Lock = asyncio.Lock()

_TryAcquireRunLock():
    if self._runLock.locked():
        raise RuntimeError("Agent is already running, refuse re-entrant call")
    return await self._runLock.acquire()
```

* **单 Agent 实例同时只能跑一个 Run**：避免 SessionComponent 的 messages、ContextComponent 的 turnIndex 被并发踩踏。
* 想要并发？请创建多个 Agent 实例，各自持有独立的 Session / Context。

## 6 AgentStreamEvent（agentStreamEvent.py）

```python
class EAgentStreamEventType(Enum):
    TURN_START    # 新一轮 ReAct 开始
    TEXT_DELTA    # LLM token 增量
    TOOL_START    # 工具开始执行（含 name + args）
    TOOL_RESULT   # 工具执行完成（成功 or 失败）
    STATE_CHANGE  # EAgentState 迁移
    ERROR         # 致命错误（含 exc_info）
    DONE          # 整个 Run 终止

class AgentStreamEvent(NamedTuple):
    type: EAgentStreamEventType
    data: dict[str, Any]
    timestamp: float
```

工厂方法（按事件类型封装构造）：

| 工厂 | 作用 |
|------|------|
| `AgentStreamEvent.TextDelta(text)` | 包装 token 增量 |
| `AgentStreamEvent.ToolStart(name, args)` | 包装工具调用前事件 |
| `AgentStreamEvent.ToolResult(name, result, success)` | 工具完成 |
| `AgentStreamEvent.StateChange(old, new)` | EAgentState 迁移 |
| `AgentStreamEvent.Error(exc)` | 错误事件，附 traceback |
| `AgentStreamEvent.Done(reason)` | 终止 |

> **不可变性**：`AgentStreamEvent` 用 NamedTuple 实现，UI/前端可放心缓存而无需 deep copy。

## 7 SimpleAgent（simpleAgent.py）

精简版 Agent，**只挂载 DataComponent + LLMComponent**，跳过工具系统与 ReAct 主循环，适合：

* 无需工具、纯 chat 的轻量场景；
* 单元测试用作 baseline；
* 嵌入到更大编排器中作为子模块。

```text
SimpleAgent(config)
  ├─ AddComponent(DataComponent)
  ├─ AddComponent(LLMComponent)
  └─ InitAllComponents()

SimpleAgent.StreamAsync(query) ──► LLMComponent.StreamAsync(messages=[query])
                                     单轮、无重试、无 ReAct、无 ToolCall
```

## 8 关键不变式

1. `_runLock` 持有期间，Session / Context / EAgentState 的写入都来自当前 Run，不会有并发污染。
2. `RunWithLifecycleAsync` 的 `try/finally` 确保 `Context.AfterTurnAsync` 与 `Logging.LogRunEnd` **必然执行**，即使主循环抛异常。
3. 任意一次 Run 结束后，`EAgentState` 一定回到终态 `FINISHED` 或 `ERROR`，不会停留在 `THINKING/ACTING`。
4. `RunInvoke / RunStream` 仅在**无运行 loop**的线程下使用，否则必须显式调用 `RunInvokeAsync / RunAsync`。
