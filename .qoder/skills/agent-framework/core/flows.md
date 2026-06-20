# 关键流程时序

按调用顺序展开 Brain Agent 的 6 大核心流程，文件指向真实实现位置。

---

## 1. Agent 初始化流程

入口：[Agent.\_\_init\_\_](file:///c:/Users/Administrator/Desktop/Brain-main/agent/agent.py#L53)

```
Agent(llm, config?)
├─ super().__init__()                       # BaseAgent 初始化空 _components 字典
├─ _buildCompleted = False
├─ _runLock = None                          # asyncio.Lock 惰性创建
│
├─ 注册 Component 序列（顺序固定）
│  ├─ AddComponent(DataComponent)
│  │   └─ DataComponent()                   # 默认 AgentConfig.Default()
│  ├─ _dataComp.llm = llm                   # 注入 LLM 句柄
│  ├─ if config: _dataComp.config = config  # 覆盖默认配置
│  ├─ AddComponent(LLMComponent)
│  ├─ AddComponent(SessionComponent)
│  ├─ AddComponent(ContextComponent)
│  ├─ AddComponent(RuleComponent)
│  ├─ AddComponent(SkillComponent)
│  ├─ AddComponent(McpComponent)
│  ├─ AddComponent(ToolComponent)
│  ├─ AddComponent(HarnessComponent)
│  └─ AddComponent(LoggingComponent)
│
└─ InitAllComponents()                      # 按挂载顺序执行 OnInitialize
   ├─ DataComponent.OnInitialize    → config.Validate() 不通过则 raise
   ├─ LLMComponent.OnInitialize     → 取 dataComp.llm；TokenEstimator.Configure(modelName)
   ├─ SessionComponent.OnInitialize → 注入 MemoryComponent (可缺省 None)
   ├─ ContextComponent.OnInitialize → 注入 Session/LLM/Data；构造 ContentStore + ContextLodManager
   ├─ RuleComponent.OnInitialize    → pass
   ├─ SkillComponent.OnInitialize   → pass
   ├─ McpComponent.OnInitialize     → pass
   ├─ ToolComponent.OnInitialize    → pass
   ├─ HarnessComponent.OnInitialize → 缓存依赖；_built=False
   └─ LoggingComponent.OnInitialize → 读取 logDir/logFormat；启动 _FlushLoopAsync
```

完成后 Agent 已具备四维调用能力，但 LOD0 装填要等到首次 `RunAsync` 时由 `HarnessComponent.BuildAsync()` 完成。

---

## 2. ReAct 核心循环

入口：[\_RunReActCoreAsync](file:///c:/Users/Administrator/Desktop/Brain-main/agent/agent.py#L199)

```
RunAsync(userMessage, cancellationToken)
├─ _runLock 惰性创建
├─ _TryAcquireRunLock() —— 非阻塞预检 (失败 yield ErrorEvent + return)
└─ async with _runLock:
   ├─ state = THINKING; yield StateChange(THINKING)
   └─ RunWithLifecycleAsync(_RunReActCoreAsync(...))
      ├─ try: yield 核心事件
      ├─ finally:
      │   ├─ ctxComp.AfterTurnAsync()          # 落盘清理 + Session 持久化
      │   ├─ loggingComp.OnAfterTurnAsync()    # 日志刷盘
      │   └─ if not normalExit: state = ERROR
      │
      └─ 核心循环 _RunReActCoreAsync ↓

_RunReActCoreAsync(userMessage, cancellationToken, streaming)
├─ 首轮装填（_buildCompleted == False）
│  ├─ await harnessComp.BuildAsync()              # LOD0 注入 + 工具加载
│  ├─ toolSpecs = toolComp.GetAllToolSpecs()
│  ├─ if toolSpecs: llmComp.BindTools(toolSpecs)  # 写入 _requestParams.tools
│  └─ _buildCompleted = True
│
├─ Manual Rule 解析
│  └─ for rule in ruleComp.MatchManualInvoke(userMessage):
│       ctxComp.Ingest(SYSTEM, rule.body, lodLevel=SUMMARIZABLE)
│
├─ ctxComp.Ingest(USER, userMessage, lodLevel=SUMMARIZABLE)
├─ loggingComp.LogRunStart(userMessage)
│
└─ for turn in range(config.maxTurns):           # ReAct 主循环
   ├─ yield TurnStart(turn)
   │
   ├─ contextMessages = await ctxComp.AssembleAsync()
   │  └─ 自动触发 CompactAsync(force=True) 若超预算
   ├─ chatMessages = _SanitizeToolMessages(contextMessages)
   │  └─ 剔除孤儿 tool_calls / 孤儿 TOOL 结果（OpenAI 校验防御）
   │
   ├─ try:
   │   ├─ async for chunk in _CallWithRetryAsync(chatMessages, turn, ct, streaming):
   │   │     ├─ 累积 chunk.content / chunk.toolCalls / chunk.usage
   │   │     └─ 实时 yield TextDelta(content, turn)
   │   └─ loggingComp.LogLLMCall(success=True)
   ├─ except Exception:
   │   ├─ state = ERROR; ctxComp.Ingest(ASSISTANT, "[Error: ...]", DISCARDABLE)
   │   ├─ loggingComp.LogLLMCall(success=False) + LogRunEnd(ERROR)
   │   └─ yield ErrorEvent + StateChange(ERROR); return
   │
   ├─ if cancellationToken.IsCancellationRequested:
   │   └─ LogRunEnd("CANCELLED") + yield ErrorEvent + return
   │
   ├─ if toolCalls:                              # ─── ACT 阶段 ───
   │   ├─ state = ACTING; yield StateChange(ACTING, turn)
   │   ├─ for tc in toolCalls:                   # 串行执行（隔离失败）
   │   │     try: result = await toolComp.DispatchAsync(tc)
   │   │     except Exception: result = ToolResult.Fail(...)  # 兜底
   │   ├─ loggingComp.LogToolExecution(...) × N
   │   │
   │   ├─ ctxComp.Ingest(ASSISTANT, content, SUMMARIZABLE, toolCalls=...)  # 必须先于 TOOL
   │   │
   │   ├─ for tc, result in zip(toolCalls, results):  # ─── OBSERVE ───
   │   │     yield ToolStart(tc.name, args, turn)
   │   │     ingestContent = ctxComp.PersistToolResult(result.ToLLMContent(), skipPersist)
   │   │     ctxComp.Ingest(TOOL, ingestContent, lodLevel=tool.resultLodLevel, toolCallId=tc.id)
   │   │     yield ToolResultEvent(tc.name, result, turn)
   │   │
   │   ├─ state = THINKING
   │   └─ continue                               # 进入下一轮
   │
   └─ else:                                      # ─── 纯文本响应：终态 ───
       ctxComp.Ingest(ASSISTANT, fullContent, SUMMARIZABLE)
       break

else:                                            # for-else: maxTurns 耗尽
   state = ERROR; LogRunEnd(ERROR)
   yield ErrorEvent + StateChange(ERROR) + Done(); return

# ---- 正常路径收尾 ----
if config.autoCompact: await ctxComp.CompactAsync()
state = FINISHED
LogRunEnd(FINISHED, totalTokens, totalDuration)
yield StateChange(FINISHED) + Done()
```

---

## 3. LLM 调用与重试

入口：[\_CallWithRetryAsync](file:///c:/Users/Administrator/Desktop/Brain-main/agent/agent.py#L427)

```
_CallWithRetryAsync(chatMessages, turn, cancellationToken, streaming)
├─ maxRetries  = config.maxRetries        (默认 3)
├─ baseDelay   = config.retryBaseDelay    (默认 1.0)
├─ maxDelay    = config.retryMaxDelay     (默认 30.0)
│
└─ for attempt in range(maxRetries + 1):
   ├─ try:
   │   ├─ if streaming:
   │   │     async for chunk in llmComp.StreamAsync(msgs, ct): yield chunk
   │   ├─ else:
   │   │     response = await llmComp.InvokeAsync(msgs, ct)
   │   │     yield ChatChunk(response.content, response.toolCalls)
   │   └─ return                            # 成功，退出循环
   │
   ├─ except LLMError as exc:
   │   ├─ if not _IsRetryable(exc): raise   # 4xx 非 429 直接抛
   │   └─ lastException = exc               # 可重试 → 走退避
   │
   ├─ except asyncio.CancelledError: raise  # 取消信号绝不吞
   │
   ├─ except (TimeoutError, ConnectionError, OSError) as exc:
   │   └─ lastException = exc               # 网络层错误重试
   │     # 注意：AttributeError 等编程错误不在白名单，立即暴露
   │
   ├─ if attempt >= maxRetries: break       # 最后一轮不再等待
   │
   ├─ if ct.IsCancellationRequested:        # 退避前检查
   │   raise LLMError("Cancelled during retry backoff")
   │
   ├─ delay = min(baseDelay * 2^attempt, maxDelay)   # 指数退避 + 上限
   ├─ Logger.Warning(f"retry {attempt+1}/{maxRetries+1}, in {delay}s")
   ├─ await asyncio.sleep(delay)
   │
   └─ if ct.IsCancellationRequested:        # 退避后再检查
       raise LLMError("Cancelled during retry backoff")

raise LLMError("exhausted all N retry attempts: {lastException}")
```

可重试判定 `_IsRetryable`：

| statusCode | 重试 |
|------------|------|
| None（网络层无状态） | ✓ |
| 429 / 500 / 502 / 503 / 504 | ✓ |
| 其他（400 / 401 / 403 / 404 ...） | ✗ |

---

## 4. 工具执行流程

由 ReAct 主循环驱动，逐工具串行调度。

```
for tc in toolCalls:                            # 来自 LLM 流式拼接
   ┌──────────────────────────────────────────────┐
   │ ToolComponent.DispatchAsync(toolCall)         │
   ├──────────────────────────────────────────────┤
   │ tool = Get(name)                              │
   │   ├─ _tools 缓存命中  → 复用                   │
   │   └─ _toolClasses → 实例化并缓存               │
   │ if tool is None: ToolResult.Fail(unknown)     │
   │                                              │
   │ timeout = 工具实例 > 工具类 > _defaultTimeout    │
   │ try:                                          │
   │   if timeout:                                 │
   │     result = await wait_for(                  │
   │         tool.ExecuteAsync(**args),            │
   │         timeout)                              │
   │   else:                                       │
   │     result = await tool.ExecuteAsync(**args)  │
   │   _RecordExecution(name, elapsed)             │
   │   return result.WithToolName(name)            │
   │ except TimeoutError:                          │
   │   return ToolResult.Fail("timed out")         │
   │ except Exception:                             │
   │   return ToolResult.Fail("execution failed")  │
   └──────────────────────────────────────────────┘
        │
        ▼
   Agent 主循环兜底 try/except                      # 防止 BaseTool 内部异常逸出
        │
        ▼
   PersistToolResult(rawContent, skipPersist)
   ├─ skipPersist 或 !enablePersist → 原样返回
   ├─ len(content) <= persistCharThreshold → 原样返回
   └─ else: ContentStore.Store(content) → "<persisted-output> 预览"
        │
        ▼
   ctxComp.Ingest(
       ERole.TOOL,
       ingestContent,
       lodLevel = tool.resultLodLevel or EXTERNAL_ONLY,
       toolCallId = tc.id,                          # 必须匹配 LLM 发起的 ToolCall.id
   )
        │
        ▼
   yield AgentStreamEvent.ToolResultEvent(name, result, turn)
```

要点：

- **Ingest 顺序**：ASSISTANT(带 tool_calls) → TOOL × N。OpenAI 会校验 tool_calls 必须在 TOOL 消息之前，缺失则 400 拒绝。
- **toolCallId 严格匹配**：与发起的 `ToolCall.id` 一致，否则被视为孤儿。
- **skipPersist**：read_file 类工具，源文件已在磁盘 → True，避免二次写入 ContentStore。

---

## 5. 上下文压缩流程

触发点：

- AssembleAsync 估算超预算时自动 `CompactAsync(force=True)`。
- 主循环正常结束（`config.autoCompact=True`）调用一次 `CompactAsync()`。
- 外部主动调用 `CompactAsync()`。

```
ContextComponent.CompactAsync(force=False)
├─ 早退：not force and not config.autoCompact → return 0
│
└─ async with _lock:                         # 串行化，防并发重入
   ├─ budget    = config.effectiveBudget
   ├─ messages  = session.GetAll()
   ├─ assembled = lodManager.AssembleMessages(messages)
   ├─ estimated = tokenEstimator.EstimateMessages(assembled)
   ├─ threshold = budget * compactThreshold      # 默认 0.85
   │
   ├─ if not force and estimated <= threshold: return 0
   │
   ├─ result = await lodManager.CompactMessagesAsync(   # ─── LLM 摘要 ───
   │      messages, threshold,
   │      oldSummary = session.CompressedSummary,       # 增量摘要：旧摘要 + 新增消息
   │  )
   │  # result.compactedIds         = 被摘要覆盖的原始消息 ID 集合
   │  # result.newSummaryMessages   = 新摘要 ContextMessage 列表（通常 1 条）
   │
   ├─ for msgId in result.compactedIds:
   │      session.MarkCompacted(msgId)         # 仅标记，不立即删除（PurgeCompacted 在 AfterTurn）
   │
   ├─ compactedMaxTurn = max(m.turnIndex for m in messages if m.id in compactedIds)
   │
   ├─ if result.newSummaryMessages:
   │      session.SetCompressedSummary(newSummary, compactedMaxTurn)   # 唯一槽位
   │  else:
   │      # 仅 LOD2 丢弃无新摘要，扩展旧摘要覆盖范围
   │      if 旧摘要 and compactedMaxTurn > _compressedUpToTurnIndex:
   │          session.SetCompressedSummary(旧摘要, compactedMaxTurn)
   │
   └─ return beforeTokens - afterTokens         # 释放的 token 数
```

下次 AssembleAsync 时：

```
if session.CompressedSummary is not None:
    upToTurn = session.CompressedUpToTurnIndex
    tail = [m for m in messages if m.turnIndex > upToTurn]
    projected = lodManager.AssembleMessages(tail)
    projected.insert(0, compressedSummary)        # 摘要置首
```

---

## 6. 生命周期保证

入口：[RunWithLifecycleAsync](file:///c:/Users/Administrator/Desktop/Brain-main/agent/agent.py#L168)

```
RunWithLifecycleAsync(coreAsyncIterator)
├─ normalExit = False
├─ try:
│   async for event in coreAsyncIterator: yield event
│   normalExit = True
│
└─ finally:                                  # 任何路径都会执行
   ├─ if ctxComp:  await ctxComp.AfterTurnAsync()
   │   ├─ ContentStore.Cleanup(olderThan=now-storeMaxAge)   # 过期外存清理
   │   ├─ session.PurgeCompacted()                          # 释放已压缩消息内存
   │   └─ session.SaveToMemory()                            # 摘要持久化到 sessions/
   │
   ├─ if loggingComp: loggingComp.OnAfterTurnAsync()
   │   └─ if logFlushPerTurn and _events: Flush()           # 日志刷盘
   │
   └─ if not normalExit: state = ERROR
```

覆盖所有终止路径：

| 路径 | 触发 | finally 行为 |
|------|------|-------------|
| 正常完成 | `Done()` 后 yield 退出 | normalExit=True，照常清理 |
| LLM 异常 | core yield ErrorEvent 后 return | normalExit=False，state=ERROR |
| maxTurns 耗尽 | core return | normalExit=False，state=ERROR |
| asyncio.CancelledError | 上层取消 | normalExit=False，state=ERROR |
| 超时（同步入口 RunStream/RunInvoke） | RunAsyncGenerator 抛 TimeoutError | finally 仍执行 |
| 用户 CancellationToken | core 主动 yield ErrorEvent + return | normalExit=False，state=ERROR |

效果：消息压缩状态、外存文件、Session 摘要、Log 缓冲均不会因异常而泄漏。

---

## 7. 流事件类型速查

事件由 [AgentStreamEvent](file:///c:/Users/Administrator/Desktop/Brain-main/agent/agentStreamEvent.py) 统一构造：

| 工厂方法 | EventType | 触发时机 |
|---------|-----------|---------|
| `TurnStart(turn)` | TURN_START | 每轮 ReAct 开始 |
| `TextDelta(content, turn)` | TEXT_DELTA | LLM 流式 chunk 含文本 |
| `ToolStart(name, args, turn)` | TOOL_START | 工具发起执行前 |
| `ToolResultEvent(name, result, turn)` | TOOL_RESULT | 工具结果 Ingest 后 |
| `StateChange(state, turn?)` | STATE_CHANGE | EAgentState 迁移 |
| `ErrorEvent(msg, turn?)` | ERROR | 异常路径 |
| `Done()` | DONE | 正常 / maxTurns 终止 |
