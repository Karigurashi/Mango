# ContextComponent 上下文引擎

> 源码：[`agent/component/contex/contextComponent.py`](../../../agent/component/contex/contextComponent.py)、[`agent/component/contex/eContextLodLevel.py`](../../../agent/component/contex/eContextLodLevel.py)、[`agent/component/contex/contextLodManager.py`](../../../agent/component/contex/contextLodManager.py)、[`agent/component/contex/contextCompactor.py`](../../../agent/component/contex/contextCompactor.py)、[`agent/component/contex/contentStore.py`](../../../agent/component/contex/contentStore.py)、[`agent/component/contex/contextMessage.py`](../../../agent/component/contex/contextMessage.py)

ContextComponent 是 Agent 框架最复杂、也最具差异化的部分：把"消息全集"按 LOD 四级动态投影成"模型可吃下"的一段 messages，并在每轮结束做微压缩、外存清理、Memory 持久化。它是**调度器**，本身不存数据；数据归属于 [SessionComponent](session.md)（账本）和 [ContentStore](#5-外存-contentstore-contentstorepy)（外存）。

## 1 模块结构

```
agent/component/contex/
├── contextComponent.py     # 四阶段对外接口 + 调度
├── eContextLodLevel.py     # LOD 四级枚举 + 行为方法
├── contextMessage.py       # ContextMessage 数据类（带 LOD/turnIndex/isAgedOut...）
├── contextLodManager.py    # 投影组装 + 增量摘要合并
├── contextCompactor.py     # 三级紧急度压缩策略（含 LLM 摘要）
└── contentStore.py         # LOD3 大结果外存（原子写 + LRU 淘汰）
```

## 2 四阶段对外接口

```text
ContextComponent
  ├─ Ingest(message)         —— USER/Tool 结果进入"账本"前的钩子（同步）
  ├─ AssembleAsync()         —— 装配 LLM 吃的 messages（含预算守卫）
  ├─ CompactAsync(force=False) —— 主动压缩（asyncio.Lock 串行化）
  └─ AfterTurnAsync()        —— 一轮结束的清理：Cleanup + Purge + SaveToMemory
```

调用时序详见 [flows.md](flows.md)；本文聚焦每个阶段的内部逻辑。

## 3 核心字段

```text
ContextComponent
  ├─ _session:        SessionComponent          # 账本只读引用
  ├─ _llmComponent:   LLMComponent              # 用于压缩 LLM 调用
  ├─ _config:         AgentConfig               # 阈值 / 预算 / 路径
  ├─ _contentStore:   ContentStore              # LOD3 外存
  ├─ _lodManager:     ContextLodManager         # 投影组装
  ├─ _compactor:      ContextCompactor          # 压缩策略
  ├─ _tokenEstimator: TokenEstimator            # 实例级估算器
  ├─ _turnIndex:      int                       # 当前轮号（每次 USER Ingest +1）
  ├─ _lastColdOffloadTurn: int                  # 上次微压缩所在轮，用于"每轮一次"
  └─ _lock:           asyncio.Lock              # CompactAsync 串行化
```

## 4 LOD 四级（eContextLodLevel.py）

```text
EContextLodLevel(IntEnum):
    RESIDENT       (0)   # System / Rules / Skill 前缀 / Memory INDEX —— 永不压缩
    SUMMARIZABLE   (1)   # 历史对话 / 重要工具结果 —— 可摘要替代
    DISCARDABLE    (2)   # 大量琐碎工具结果 —— 直接丢弃
    EXTERNAL_ONLY  (3)   # 大文本/二进制 —— 已落盘，仅保留路径引用
```

| 行为方法 | 语义 |
|---------|------|
| `CanCompress` | LOD ≥ 1 |
| `CanDiscard` | LOD ≥ 2 |
| `IsTurnScoped` | LOD ≥ 2（仅当轮可见，下一轮不再注入） |

## 5 ContextMessage 数据类（contextMessage.py）

```text
@dataclass(slots=True)
ContextMessage:
  ├─ _chatMessage:   ChatMessage           # role + content + tool_calls 原文
  ├─ lodLevel:       EContextLodLevel      # 投影时控制可见性
  ├─ turnIndex:      int                   # 隶属哪一轮
  ├─ messageId:      str (uuid)            # 唯一标识，用于 Session.FindById
  ├─ summarizedFrom: list[str]             # 若是摘要消息，原始消息 id 列表
  ├─ isCompacted:    bool                  # 已被压缩替代（待 PurgeCompacted）
  └─ isAgedOut:      bool                  # 已 ageout，仅以投影形式注入
```

```text
工厂 / 工具方法：
  Create(chat, lod, turnIndex, ...)      # 自动生成 messageId
  Clone()                                # 深拷贝（用于不可变投影）
  CreateAgedOutProjection()              # 生成 ageout 后的占位
  MarkAgedOut()                          # 原地标记
  EstimateTokens()                       # 缓存估算结果，避免重复计算
```

> `slots=True` + 缓存 token 估算：每条消息内存占用极小，估算只算一次，长会话仍可线性扫描。

## 6 ContentStore 外存（contentStore.py）

LOD3 大内容的落盘存储，与 Context 解耦。

| 方法 | 行为 |
|------|------|
| `Store(content) -> filePath` | **原子写**（tempfile + os.replace），超容量先 LRU 淘汰最旧文件 |
| `Load(path) -> str \| None` | 按相对路径读，支持绝对路径 |
| `GetSummary(path, maxChars=200)` | 取前 N 字符做摘要 |
| `Cleanup(olderThan=None)` | 按 mtime 清理 |
| `GetTotalSize()` | 带脏标位缓存的总字节数（避免高频 O(N) 全扫） |
| `BuildPathReference(path, size, summary)` | 生成 LOD3 引用文案（带"用 read 工具读取"提示） |
| `BuildPersistedPreview(path, content, previewChars=500)` | Claude Code `<persisted-output>` 风格预览块 |

容量水位由 `AgentConfig`：
* `contextStoreMaxFileSize`（默认 10MB，单文件超限截断）
* `contextStoreMaxTotalSize`（默认 500MB，总量超限 LRU 淘汰）

## 7 ContextLodManager 投影组装（contextLodManager.py）

### 7.1 工具结果分级 `ClassifyToolResult`

```text
ClassifyToolResult(content, toolName) -> EContextLodLevel
  ├─ 行数 > config.lod3LineThreshold  ──► EXTERNAL_ONLY  (LOD3，落盘)
  ├─ 字节数 > config.lod3SizeThreshold ──► EXTERNAL_ONLY
  ├─ category in {SHELL, NETWORK}      ──► DISCARDABLE   (LOD2)
  └─ default                            ──► SUMMARIZABLE  (LOD1)
```

### 7.2 投影 `AssembleMessages`

```text
AssembleMessages(allMessages, currentTurn) -> list[ChatMessage]:
  for m in allMessages:
    skip if m.isCompacted              # 已被压缩替代的不再投影
    if m.lodLevel == LOD3 and m.turnIndex < currentTurn:
        skip                           # LOD3 仅当轮可见
    if m.isAgedOut:
        yield CreateAgedOutProjection(m)   # 占位文本 "[消息已老化]"
    else:
        yield m._chatMessage
```

### 7.3 增量摘要合并 `CompactMessagesAsync`

旧摘要 + 当轮未压缩 LOD1 → **单条新摘要**（始终只有一条 compressedSummary）。这是为了避免摘要消息无限增长，长会话也能保持稳定的 Header 大小。

## 8 ContextCompactor 压缩策略（contextCompactor.py）

按 token 占用比 `currentTokens / targetTokens` 分三级紧急度（`ECompactionUrgency`）：

| 紧急度 | 触发条件 | 策略 |
|--------|---------|------|
| `MILD` | 1.0 < ratio ≤ 1.5 | **不调 LLM**：丢弃热尾窗口外的 LOD2，O(n) 双遍扫描 |
| `MODERATE` | 1.5 < ratio ≤ 2.0 | 丢冷 LOD2 + LLM **逐条**摘要最旧 LOD1 |
| `SEVERE` | ratio > 2.0 | 丢冷 LOD2 + LLM **批量**摘要全部 LOD1（合并为单条摘要消息）|

### 8.1 热尾窗口

```text
hotWindow = [latestTurn - keepRecentTurns + 1, latestTurn]
hotLod2  = LOD2 ∩ hotWindow      # 保留
coldLod2 = LOD2 \ hotWindow      # 丢弃
```

### 8.2 LLM 摘要兜底

* 单条摘要超时 / 异常 ──► 截断为前 `summaryMaxTokens * 4` 字符；
* 批量摘要同理用 `batchSummaryMaxTokens * 4`；
* `_COMPACTION_TIMEOUT = 60s`：压缩 LLM 调用整体超时，防止压缩流程卡死主循环。

### 8.3 增量批量压缩 `CompactBatchAsync`

供 `ContextComponent.CompactAsync(force=True)` 使用：**始终把所有 LOD1 合并为单条摘要**，无条件执行；与 LOD 三级紧急度的 `CompactByLodAsync` 互补。

## 9 四阶段实现细节

### 9.1 Ingest（同步）

```text
Ingest(message):
  if message.role == USER:
      self._turnIndex += 1
  Session.Append(message)        # 真正写入账本
```

### 9.2 AssembleAsync

```text
AssembleAsync() -> list[ChatMessage]:
  messages = compressedSummary + lodManager.AssembleMessages(Session.GetAll(), turnIndex)
  if EstimateTokens(messages) > effectiveBudget:
      await self.CompactAsync(force=True)            # 串行压缩
      messages = ... 重新组装 ...
  if EstimateTokens(messages) > effectiveBudget:
      messages = self._TrimToBudget(messages)        # O(n) 硬兜底
  return messages
```

### 9.3 CompactAsync

```text
async with self._lock:                             # 关键：同 Agent 内串行化
    if force:
        result = await compactor.CompactBatchAsync(...)
    else:
        result = await compactor.CompactByLodAsync(...)
    Session.MarkCompacted(result.compactedIds)
    Session.SetCompressedSummary(result.newSummaryMessages)
```

### 9.4 AfterTurnAsync

```text
AfterTurnAsync():
  ├─ self._OffloadColdLod2()                       # 每轮一次微压缩（见 §10）
  ├─ ContentStore.Cleanup(olderThan=now - TTL)
  ├─ Session.PurgeCompacted()                      # 真正回收已 compacted 消息
  └─ Memory.SaveSessionSummary(...)                # 跨会话持久化
```

## 10 微压缩 `_OffloadColdLod2`

```text
_OffloadColdLod2():
  if turnIndex == _lastColdOffloadTurn:           # 每轮最多一次
      return
  threshold = turnIndex - keepRecentTurns + 1
  for m in Session messages where lod==LOD2 and turn < threshold:
      m.MarkAgedOut()                             # 原地标记，不删除
  _lastColdOffloadTurn = turnIndex
```

> 这是为了让"温和压缩"在 budget 还没爆炸前就持续进行，**不调用 LLM**，O(n) 一次扫描。

## 11 PersistToolResult（大结果落盘）

```text
PersistToolResult(toolResult):
  if not _ShouldPersist(toolResult):
      return toolResult                            # 直接返回原对象
  path = ContentStore.Store(toolResult.content)
  preview = ContentStore.BuildPersistedPreview(path, content)
  return ToolResult(content=preview, ...)          # content 已替换为 <persisted-output> 块
```

判定标准与 `ClassifyToolResult` 同：行数/字节数超阈值 → 落盘。

## 12 并发与不变式

| 不变式 | 说明 |
|--------|------|
| `_lock` 串行化 CompactAsync | 同 Agent 内不会有两路压缩同时改 Session.compressedSummary |
| 始终只有 1 条 compressedSummary | `CompactBatchAsync` 增量合并保证 |
| LOD3 仅当轮可见 | 避免大文件路径反复占用预算 |
| `_turnIndex` 单调递增 | 仅在 `Ingest(USER)` 时 +1 |
| 硬兜底 `_TrimToBudget` | 即便 LLM 摘要失败，也保证 messages 不超 budget |
| 微压缩每轮最多一次 | 用 `_lastColdOffloadTurn` 去重，O(n) |
