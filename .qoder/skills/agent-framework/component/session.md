# SessionComponent 会话管理

> 源码：[`agent/component/session/sessionComponent.py`](../../../agent/component/session/sessionComponent.py)

SessionComponent 是 Agent 框架内**消息的唯一归属地**——所有 USER/ASSISTANT/TOOL 消息只在这里持久化。ContextComponent 不持有消息，只通过 SessionComponent 投影组装；MemoryComponent 在 Run 结束时从这里抽取摘要写入跨会话记忆。它和 [ContextComponent](contex.md) 的分工严格遵守 **账本 vs 调度器** 的职责切分。

## 1 字段

```text
SessionComponent
  ├─ sessionId:                str (uuid4)               # 整个会话生命周期不变
  ├─ messages:                 list[ContextMessage]      # 顺序追加的消息总集
  ├─ _messageIndex:            dict[messageId, int]      # O(1) FindById 索引
  ├─ _compressedSummary:       ContextMessage | None     # 当前唯一的"历史摘要"消息
  ├─ _compressedUpToTurnIndex: int                       # 摘要覆盖到的最大 turnIndex
  ├─ _compressedMessageIds:    set[str]                  # 摘要替代了哪些原始消息 id
  ├─ memory:                   MemoryComponent | None    # OnInitialize 注入
  └─ _tokenEstimator:          TokenEstimator
```

> **设计要点**：`_messageIndex` 与 `messages` 同步维护，使 `FindById` 退化为 O(1)，避免长会话场景下 ReAct 主循环高频查找带来的 O(n²) 退化。

## 2 OnInitialize 依赖注入

```text
OnInitialize(agent):
    self.memory = agent.GetComponent(MemoryComponent)   # 可能为 None（按需挂载）
    # 不主动加载历史 session，由 Memory 提供 INDEX 后由 LLM 决定
```

## 3 消息管理 API

| 方法 | 行为 |
|------|------|
| `Append(msg)` | 追加单条；同步更新 `_messageIndex` |
| `AppendBatch(msgs)` | 批量追加，仅一次索引重建（性能优化） |
| `GetAll() -> list` | 返回引用（**调用方禁止修改**） |
| `GetLastN(n) -> list` | 截取最近 n 条，常用于 fallback 摘要 |
| `FindById(messageId) -> ContextMessage \| None` | O(1) 查找 |
| `Clear()` | 清空所有消息（保留 sessionId）|

> 不暴露 `pop` / `__setitem__`：所有"删除"必须经 `MarkCompacted` → `PurgeCompacted` 两步走，保证可观测且原子。

## 4 压缩与摘要

### 4.1 标记-清理两阶段

```text
MarkCompacted(messageIds: Iterable[str]):
    ├─ 把 _messageIndex 中找到的消息 .isCompacted = True
    └─ self._compressedMessageIds |= messageIds   # 累加到摘要覆盖集

PurgeCompacted():
    ├─ 真正从 messages 列表中删除所有 isCompacted=True 的消息
    └─ 重建 _messageIndex
```

* `MarkCompacted` 与 `PurgeCompacted` 分两步：CompactAsync 期间只标不删，AfterTurnAsync 阶段统一回收，避免压缩中途消息消失导致 ContextLodManager 投影错乱。

### 4.2 唯一压缩摘要

```text
SetCompressedSummary(newSummaryMessages: list[ContextMessage]):
    ├─ 至多一条新摘要（CompactBatchAsync 保证）
    ├─ 旧摘要被替换（不累加）
    ├─ _compressedUpToTurnIndex = max(_compressedUpToTurnIndex, latestTurn)
    └─ _compressedMessageIds 累计被压缩消息 id

ClearCompressedSummary():
    ├─ _compressedSummary = None
    ├─ _compressedUpToTurnIndex = -1
    └─ _compressedMessageIds.clear()

@property compressedSummary -> ContextMessage | None
```

> **始终只有 0 或 1 条压缩摘要**——这是上下文引擎稳定性的关键约束。

## 5 持久化 `SaveToMemory`

```text
SaveToMemory(self):
    if self.memory is None:
        return
    summaryText = self._ExtractSessionSummary()    # 拼接当前可见消息 + compressedSummary
    self.memory.SaveSessionSummary(self.sessionId, summaryText)
```

由 `ContextComponent.AfterTurnAsync` 在每轮结束（或 Run 结束）调用，**写入 `<memoryDir>/sessions/{sessionId}.md`**，由 MemoryStore 的 LRU 策略自动裁剪老会话。

`_ExtractSessionSummary` 内部规则：
* 优先包含 `_compressedSummary.content`；
* 追加最近若干条非 LOD3 消息原文；
* 截断到 `summaryMaxTokens * 4` 字符兜底。

## 6 与 ContextComponent 的分工

| 职责 | Session | Context |
|------|---------|---------|
| 持有消息总集 | ✅ | ❌（只读引用） |
| 消息追加 | ✅ Append | ❌ |
| 消息分级 LOD | ❌ | ✅ ContextLodManager |
| 投影组装为 LLM messages | ❌ | ✅ AssembleAsync |
| 压缩决策 | ❌ | ✅ CompactAsync |
| 标记被压缩 | ✅ MarkCompacted | 调用 Session 的此方法 |
| 实际删除 | ✅ PurgeCompacted | 同上 |
| 摘要存储 | ✅ _compressedSummary | 写入 Session |
| 跨会话持久化 | ✅ SaveToMemory | 调用 Session 的此方法 |

> **一句话**：Session = 账本（数据 + 标记 + 删除），Context = 调度器（分级 + 投影 + 压缩 + 协调）。

## 7 与其他组件的关系

```text
HarnessComponent.BuildAsync
    └─► Session.AppendBatch(LOD0 系统消息)        # 注入 system / Memory INDEX 等

Agent._RunReActCoreAsync
    ├─► Context.Ingest(USER)        ──► Session.Append
    ├─► Context.AssembleAsync       ──► Session.GetAll() 投影组装
    ├─► tool_call → DispatchAsync   ──► Session.Append(TOOL result)
    ├─► Context.CompactAsync        ──► Session.MarkCompacted + SetCompressedSummary
    └─► Context.AfterTurnAsync      ──► Session.PurgeCompacted + SaveToMemory
```

## 8 关键不变式

1. `_messageIndex` 与 `messages` **始终同步**（Append/Purge 路径都更新）。
2. **任意时刻最多 1 条 compressedSummary**。
3. `MarkCompacted` 后到 `PurgeCompacted` 之间，消息仍存在于 `messages`，但 `isCompacted=True`，投影时会被 ContextLodManager 跳过。
4. `sessionId` 在整个 Session 生命周期不变；`Clear` 不会重置它。
5. **不暴露原地修改接口**：所有变更必须走 `Append/MarkCompacted/PurgeCompacted/SetCompressedSummary` 四个明确入口，方便日志与回放。
