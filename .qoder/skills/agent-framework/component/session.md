# SessionComponent 会话管理

Agent 框架内消息的唯一归属地。所有 USER/ASSISTANT/TOOL 消息只在这里持久化。ContextComponent 不持有消息，只通过 SessionComponent 读取组装。

## Session 数据容器

纯数据容器，封装单次会话的全部消息与索引：

- `messages`：顺序追加的消息总集
- `_messageIndex`：messageId → msg，O(1) 查找
- `lod0Messages`：RESIDENT 快速索引（压缩时不可触碰）
- `_lod3Count`：LOD3 消息计数（为 0 时跳过扫描）

Append 时同步维护所有索引。

## 压缩回写

`ApplyCompactionResult(messages)`：Clear(保留 LOD0) → 追加非 LOD0 消息，一步替换。替代旧版 MarkCompacted + PurgeCompacted 两步走。

## 孤儿修复

`FixOrphanedToolCalls`：单趟反向遍历，收集有效 TOOL 的 toolCallId → 两指针过滤 ASSISTANT 的 toolCalls → 删除空壳 ASSISTANT。压缩后由 AssembleAsync 调用。

## LOD3 清理

`RemoveExpiredLod3(currentTurn)`：LOD3 = 当轮注入次轮丢弃。级联删除空壳 ASSISTANT 避免残留。

## 多会话管理

SessionComponent 管理多个 Session，一个 Agent 可持有多个会话。NewSession 时拷贝旧会话 LOD0 到新会话（System 规则等跨会话复用）。SwitchSession 切换前自动归档。

## 持久化

SaveToMemory：优先取 turnIndex=-1 的摘要消息内容，无摘要时取最后一条 ASSISTANT 消息，截断到 token 预算后写入 `sessions/{sessionId}.md`。由 AfterTurnAsync 每轮结束调用。

## Session vs Context 分工

| 职责 | Session | Context |
|------|---------|---------|
| 持有消息总集 | ✅ | 只读引用 |
| 消息追加 | ✅ | 调 Session.Append |
| 消息分级 LOD | | ✅ |
| 组装 LLM messages | | ✅ |
| 压缩决策 | | ✅ |
| 压缩回写 | ✅ | 调用此方法 |
| 孤儿修复 | ✅ | 调用此方法 |
| LOD3 清理 | ✅ | 调用此方法 |
| 持久化 | ✅ | 调用此方法 |

一句话：Session = 账本（数据 + 回写 + 清理），Context = 调度器（分级 + 组装 + 压缩 + 协调）。

## 关键设计

- `_messageIndex` 与 `messages` 始终同步。
- 摘要以 turnIndex=-1 的 SYSTEM 消息存储在 messages 列表。
- `_lod3Count` 计数器避免无 LOD3 时全量扫描。
- sessionId 为 `uuid4().int`，全生命周期不变。
- LOD0 跨会话复用。
