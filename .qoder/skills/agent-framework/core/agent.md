# Agent 执行流

Agent 是把 Core 容器、各 Component 与 LLM 协议串成可执行 Agent 的编排器，负责组件挂载、双模调用入口、ReAct 主循环、事件分发、并发与重试兜底。

## Agent 构造流程

```
Agent(llm, config?)
├─ AddComponent(DataComponent)          # 仅构造，预注入 llm + config
├─ GetComponent(EventBusComponent)      # 惰性触发 OnInitialize
├─ GetComponent(LLMComponent)           # 注入 Data.llm + EventBus
├─ GetComponent(SessionComponent)       # 创建默认 Session
├─ GetComponent(ContextComponent)       # 注入 Session/LLM/Data/EventBus
├─ GetComponent(RuleComponent)
├─ GetComponent(SkillComponent)
├─ GetComponent(McpComponent)
├─ GetComponent(ToolComponent)
└─ GetComponent(HarnessComponent)       # 缓存全部依赖，_built=False
```

LOD0 装填延迟到首次 RunStreamAsync/RunAsync 时由 HarnessComponent.BuildAsync() 完成。

## 双模调用入口

RunStreamAsync 与 RunAsync 共享 `_RunGuardedAsync` 统一入口，区别仅在于 LLM 调用方式（StreamAsync vs InvokeAsync）。

**`_RunGuardedAsync` 流程**：

```
_RunGuardedAsync(userMessage, cancellationToken, stream)
├─ _runLock 惰性创建（asyncio.Lock）
├─ 若 _runLock.locked() → 推送 ErrorEvent + return
├─ async with _runLock:
│   ├─ _RunReActCoreAsync(userMessage, ct, stream)
│   └─ finally:
│         ctxComp.AfterTurnAsync()           # LOD3清理 + SaveToMemory
│         若异常退出 → state=ERROR + EmitDone
```

## ReAct 核心循环

```
准备阶段：
  harnessComp.BuildAsync()                    # LOD0装填 + 工具绑定
  ctxComp.AutoColdOffloadIfNeeded()           # 宽限期冷卸载检查
  ctxComp.Ingest(USER, userMessage)

for turn in range(maxTurns):
  ┌─ THINK ──────────────────────────────┐
  │ EmitEvent(TurnStart)                   │
  │ chatMessages = ctxComp.AssembleAsync() │
  │   → 增量估算 + 超预算自动压缩          │
  │   → FixOrphanedToolCalls              │
  │   → _ApplyCacheControl                │
  │ llmComp.StreamAsync / InvokeAsync     │
  │   → 内部推送 ThinkingDelta/TextDelta   │
  └───────────────────────────────────────┘
         │
         ├─ 无 toolCalls → 纯文本响应 → break
         │
  ┌─ ACT ────────────────────────────────┐
  │ EmitStateChange(ACTING)               │
  │ for tc: EmitEvent(ToolStart)          │
  │ results = toolComp.DispatchBatchAsync()│
  │ for tc, result: EmitEvent(ToolResult) │
  │ ctxComp.Ingest(ASSISTANT, toolCalls)  │
  │ for result:                           │
  │   ingestContent = PersistToolResult() │
  │   ctxComp.Ingest(TOOL, ingestContent) │
  │ ctxComp.AdvanceTurn()                 │
  └───────────────────────────────────────┘
         │
         └─ continue

maxTurns耗尽 → ErrorEvent + ERROR + Done
正常结束 → autoCompact触发 → FINISHED + Done
```

### Ingest 顺序约束

ASSISTANT(带 tool_calls) 必须在 TOOL 消息之前 Ingest。OpenAI 校验 tool_calls 在 TOOL 消息之前，缺失则 400 拒绝。

### 异常处理

| 机制 | 行为 |
|------|------|
| LLM 异常 | ErrorEvent + STATE_CHANGE(ERROR) |
| CancellationToken 取消 | ErrorEvent + STATE_CHANGE(ERROR) |
| maxTurns 耗尽 | ErrorEvent + STATE_CHANGE(ERROR) + Done |
| finally | ctxComp.AfterTurnAsync() 必然执行 |

## 并发安全

`_runLock`（asyncio.Lock）保证单 Agent 实例同时只能跑一个 Run，避免 Session 的 messages、Context 的 turnIndex 被并发踩踏。想并发需创建多个 Agent 实例。

## 事件系统

事件通过 EventBusComponent 推送，替代旧版 yield 模式：

- **Subscribe(callback)**：注册同步回调
- **Push(event)**：广播所有监听器 → 自动归还对象池
- **监听器异常隔离**：不中断 Agent 主循环

### AgentStreamEvent 事件类型

| 事件 | 触发时机 |
|------|---------|
| TURN_START | 每轮 ReAct 开始 |
| THINKING_DELTA | 流式思考增量 |
| THINKING_COMPLETE | 思考完成 |
| TEXT_DELTA | 流式文本增量 |
| TEXT_COMPLETE | 文本完成 |
| TOOL_START | 工具调用开始 |
| TOOL_RESULT | 工具执行结果 |
| STATE_CHANGE | EAgentState 迁移 |
| COMPACTION | 上下文压缩 |
| ERROR | 错误事件 |
| DONE | 本轮结束 |

### 对象池

事件从对象池获取（最大 64 个），Push 后自动 Release 归还。调用方 MUST NOT 在回调返回后继续持有 event 引用。

### 事件推送内聚

LLMComponent.StreamAsync 内部直接推送 ThinkingDelta / TextDelta / ThinkingComplete / TextComplete，Agent 主循环无需自行管理缓冲区。

## 生命周期保证

`_RunGuardedAsync` 的 try/finally 覆盖所有终止路径：

| 路径 | finally 行为 |
|------|-------------|
| 正常完成 | AfterTurnAsync 照常清理 |
| LLM 异常 | state=ERROR + EmitDone |
| maxTurns 耗尽 | state=ERROR + EmitDone |
| CancellationToken 取消 | state=ERROR + EmitDone |

任意一次 Run 结束后 EAgentState 一定回到终态 FINISHED 或 ERROR。消息压缩状态、外存文件、Session 摘要不因异常泄漏。

## 工具执行流程

```
DispatchBatchAsync(toolCalls)
├─ asyncio.gather 并发调度
├─ 单工具流程：
│   tool = Get(toolCall.name)
│   tool._agent = self._agent              # 注入 Agent 引用
│   timeout 三级优先：实例 > 类 > default(300s)
│   await asyncio.wait_for(tool.ExecuteAsync(**args), timeout)
│   异常包装为 ToolResult.Fail
├─ 单工具失败不取消其余任务
└─ 返回与输入顺序对应的 ToolResult 列表
```

## 上下文压缩流程

触发点：AssembleAsync 增量估算超预算自动 CompactAsync(force=True)；主循环正常结束 autoCompact 触发；每轮对话前 AutoColdOffloadIfNeeded。

```
CompactAsync(force=False)
├─ asyncio.Lock 串行化
├─ 优先级1: 冷 LOD2 落盘为路径引用（零LLM成本）
├─ 优先级2: LOD1 → LLM 批量摘要 → SYSTEM 摘要消息
└─ session.ApplyCompactionResult（保留LOD0）
```

压缩后 FixOrphanedToolCalls 净化孤儿工具消息。

## SimpleAgent

仅挂载 DataComponent + LLMComponent + EventBusComponent。RunStreamAsync 单轮调 LLMComponent.StreamAsync，事件经 EventBusComponent 推送。无 ReAct、无工具、无 Context、无 Harness。
