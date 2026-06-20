# LoggingComponent 结构化日志

> 源码：[`agent/component/logging/loggingComponent.py`](../../../agent/component/logging/loggingComponent.py)、[`agent/component/logging/logEvent.py`](../../../agent/component/logging/logEvent.py)、[`agent/component/logging/eLogEventType.py`](../../../agent/component/logging/eLogEventType.py)、[`agent/component/logging/eLogLevel.py`](../../../agent/component/logging/eLogLevel.py)

LoggingComponent 是 Agent 框架内的**结构化观测层**：把 LLM 调用、工具执行、上下文压缩、状态迁移等关键事件以六大类 `LogEvent` 为粒度统一采集，按 TEXT 与 JSONL 双格式落盘，支持后台异步刷盘、采样率、Run/Turn 维度指标聚合，是排障 / 性能分析 / 计费的核心数据源。

## 1 模块结构

```
agent/component/logging/
├── loggingComponent.py     # 顶层：采集 / 缓冲 / 刷盘 / 指标
├── logEvent.py             # LogEvent 数据类（slots，三种序列化）
├── eLogEventType.py        # 七个事件类型（IntEnum）
└── eLogLevel.py            # INFO / WARNING / ERROR
```

## 2 ELogEventType（eLogEventType.py）

```text
ELogEventType(IntEnum):
    LLM_CALL          = 0   # LLM 调用完成（流式 / 非流式）
    TOOL_EXECUTION    = 1   # 工具执行完成（含失败）
    COMPACTION        = 2   # 上下文压缩完成
    STATE_CHANGE      = 3   # EAgentState 迁移
    CONTEXT_LIFECYCLE = 4   # Ingest / Assemble / Compact / AfterTurn 钩子
    RUN_START         = 5   # 单次 Run 启动
    RUN_END           = 6   # 单次 Run 结束（正常/异常/超限）
```

## 3 ELogLevel（eLogLevel.py）

```text
ELogLevel(IntEnum):
    INFO    = 0   # 默认
    WARNING = 1   # 重试 / 超时回退等
    ERROR   = 2   # 调用失败 / Run 异常结束
```

## 4 LogEvent 数据结构（logEvent.py）

```text
class LogEvent:
    __slots__ = ("timestamp", "wallTime", "eventType",
                 "sessionId", "turnIndex", "duration", "metadata")

    timestamp:  float          # time.monotonic()，仅用于差值计算
    wallTime:   float          # time.time()，用于人类可读时间
    eventType:  ELogEventType
    sessionId:  str
    turnIndex:  int
    duration:   float | None   # 持续时长（LLM/工具/压缩耗时）
    metadata:   dict           # 事件特定数据

    序列化：
      ToDict()      → dict（用于 JSONL）
      ToJsonLine()  → str（单行 JSON + "\n"）
      ToTextLine()  → str（人类可读 "[wallTime] EVENT_TYPE | session=...| ...")
```

> `__slots__` 把每条日志的内存开销压到最低；长 Run 即便采集十万级事件也不会撑爆。

## 5 LoggingComponent（loggingComponent.py）

### 5.1 字段

```text
LoggingComponent
  ├─ _events:           list[LogEvent]            # 待刷盘缓冲
  ├─ _eventsLock:       asyncio.Lock              # 缓冲读写互斥
  ├─ _logDir:           str
  ├─ _logFilePath:      str                       # "{sessionId8}_{epoch}.log"
  ├─ _jsonlFilePath:    str                       # 同上 ".jsonl"
  ├─ _logLevel:         ELogLevel
  ├─ _logFormat:        "text" | "json" | "both"
  ├─ _sampleRate:       float                     # [0, 1]
  ├─ _flushIntervalSec: float                     # 默认 5.0
  ├─ _flushTask:        asyncio.Task | None       # 后台周期刷盘任务
  ├─ _runMetrics:       dict[turnIndex, dict]     # 单 Run 内各轮聚合指标
  └─ _sessionMetrics:   dict[sessionId, dict]     # 整个 Session 聚合
```

### 5.2 OnInitialize

```text
OnInitialize(agent):
    data = agent.GetComponent(DataComponent)
    self._logLevel        = data.Config.logLevel
    self._logFormat       = data.Config.logFormat
    self._sampleRate      = data.Config.logSampleRate
    self._flushIntervalSec= data.Config.logFlushInterval
    self._logDir          = data.Config.loggingDir

    sessionId8 = session.sessionId[:8]
    epoch      = int(time.time())
    self._logFilePath   = f"{logDir}/{sessionId8}_{epoch}.log"
    self._jsonlFilePath = f"{logDir}/{sessionId8}_{epoch}.jsonl"

    self._StartFlushTask()                    # 启动后台 _FlushLoopAsync
```

### 5.3 六类事件采集 API

| 方法 | 触发方 | 关键 metadata |
|------|--------|---------------|
| `LogRunStart(query)` | Agent 入口 | query, agentClass |
| `LogRunEnd(state, error?)` | Agent 出口 | finalState, totalTokens, duration, error |
| `LogLLMCall(model, in, out, dur, err?)` | LLMComponent | inputTokens / outputTokens / durationMs / error |
| `LogToolExecution(name, success, dur, err?)` | ToolComponent | toolName / category / success / durationMs |
| `LogCompaction(urgency, before, after, dur)` | ContextCompactor | urgencyLevel / tokensBefore / tokensAfter / messagesCompacted |
| `LogStateChange(old, new)` | DataComponent.State setter | from / to / valid（是否合法迁移） |
| `LogContextLifecycle(phase, ...)` | ContextComponent | phase = ingest/assemble/compact/afterTurn |
| `LogCustom(eventType, **fields)` | 任意 | 自定义扩展 |

### 5.4 采样与级别过滤

```text
_ShouldRecord(event):
    if event.level < self._logLevel: return False
    if event.eventType in {RUN_START, RUN_END}: return True   # 关键事件不采样
    return random.random() < self._sampleRate
```

### 5.5 后台刷盘 `_FlushLoopAsync`

```text
async _FlushLoopAsync():
    while True:
        await asyncio.sleep(self._flushIntervalSec)
        await self._FlushAsync()

_FlushAsync():
    async with self._eventsLock:
        pending = self._events
        self._events = []
    if not pending: return
    if "text" or "both": append events.ToTextLine() 到 _logFilePath
    if "json" or "both": append events.ToJsonLine() 到 _jsonlFilePath
```

### 5.6 三种刷盘策略

| 策略 | 时机 | 角色 |
|------|------|------|
| **后台周期** | 每 `_flushIntervalSec` 秒 | 主力，保证近实时落盘 |
| **每轮强制** | `OnAfterTurnAsync()` 由 ContextComponent 调用 | 防止某轮日志在崩溃时丢失 |
| **OnDestroy** | 组件销毁时同步刷一次 | 兜底，确保 Agent 退出无残留 |

### 5.7 指标聚合

```text
GetTurnMetrics(turnIndex) -> dict:
    返回当轮 {llmCalls, toolCalls, compactionCount, totalLatencyMs, tokensIn/Out, errors}

GetSessionMetrics() -> dict:
    返回整个 Session 累加值
```

* 在 `Log*` 时同步累加，**不二次扫描事件列表**——保证 `O(1)` 写、`O(1)` 查询。

### 5.8 运行时调参

| 方法 | 作用 |
|------|------|
| `SetLogLevel(level)` | 临时拉高/拉低观测粒度 |
| `SetSampleRate(rate)` | 灰度采样调整 |
| `SetFlushInterval(sec)` | 切换"近实时"与"批量" |

## 6 文件命名

```text
{loggingDir}/{sessionId[:8]}_{epoch}.log     # 人类可读 TEXT
{loggingDir}/{sessionId[:8]}_{epoch}.jsonl   # 机器消费 JSONL
```

每个 Session 的两个文件成对存在；多 Session 文件名通过 `sessionId8` + `epoch` 双字段冲突概率极低。

## 7 与其他组件的关系

```text
Agent.RunWithLifecycleAsync
  ├─ LogRunStart                    ──► LoggingComponent
  ├─ ReAct 循环
  │     ├─ LogStateChange (THINKING/ACTING)
  │     ├─ LogLLMCall (每次 LLM)
  │     ├─ LogToolExecution (每次工具)
  │     └─ LogCompaction (每次 CompactAsync)
  ├─ Context.AfterTurnAsync ──► OnAfterTurnAsync 强制刷盘
  └─ LogRunEnd

Agent.Destroy
  └─ LoggingComponent.OnDestroy ──► 同步刷盘 + 取消 _flushTask
```

## 8 关键不变式

1. **`__slots__` LogEvent**：单事件 < 200 bytes，长 Run 不会因日志撑爆内存。
2. **采样不丢关键事件**：`RUN_START / RUN_END / ERROR` 永远 100% 采集。
3. **三层刷盘冗余**：后台周期 + 每轮强制 + OnDestroy，保证日志在任何崩溃路径都能落盘。
4. **TEXT/JSONL 双轨**：TEXT 给人看，JSONL 给程序消费（仪表盘/告警/计费）；两份内容**事件等价**。
5. **指标聚合在采集时增量计算**：避免事后扫日志的二次开销，长 Run 也能 O(1) 读指标。
6. **后台刷盘 Task 不抛**：内部 try/except 兜底，IO 异常仅记到 Logger.Warning，不影响主循环。
