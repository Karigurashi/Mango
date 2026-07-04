# ContextComponent 上下文引擎

Session 与 LLM 之间的调度器。不存储消息（消息归属 SessionComponent），只负责四阶段生命周期：Ingest → Assemble → Compact → AfterTurn。

## LOD 四级分级

| LOD | 名称 | 压缩策略 | 丢弃策略 | 典型内容 |
|-----|------|---------|---------|---------|
| 0 | RESIDENT | 不压缩 | 不丢弃 | System Prompt、Memory INDEX |
| 1 | SUMMARIZABLE | LLM 批量摘要 | 不丢弃 | USER / ASSISTANT 消息 |
| 2 | DISCARDABLE | 冷卸载落盘 | 可丢弃 | 工具结果 |
| 3 | EXTERNAL_ONLY | 不压缩 | 次轮自动删除 | Skill 正文、规则正文 |

LOD 决定压缩优先级：冷卸载先处理 LOD2（零 LLM 成本），LLM 摘要再处理 LOD1。LOD0 任何情况下不可触碰。

## 四阶段生命周期

### 1. Ingest

将消息写入 SessionComponent。按 role 自动判定默认 LOD 等级（SYSTEM→RESIDENT，TOOL→DISCARDABLE，USER/ASSISTANT→SUMMARIZABLE）。USER 消息触发轮次递增。

### 1.5. PersistToolResult

工具结果超过字符阈值时落盘到 ContentStore，仅保留预览文本注入 LLM。

### 2. AssembleAsync

从 Session 获取消息，组装为 LLM 可消费的 ChatMessage 列表。

核心优化——**增量估算**：以 LLM 返回的真实 promptTokens 为基准，仅估算新增消息的 delta，避免每轮全量估算。冷卸载/压缩后重置基准强制全量重估。

超预算时自动触发 CompactAsync(force=True)，然后 FixOrphanedToolCalls 净化孤儿工具消息。

`_ApplyCacheControl`：在连续 RESIDENT 前缀末尾打 cacheControl 标记，配合 Anthropic Prompt Caching。

### 3. CompactAsync

**两优先级容量管理**，从低成本到高成本逐级早退：

| 优先级 | 策略 | LLM 成本 | 处理对象 |
|--------|------|---------|---------|
| 1 | 冷 LOD2 落盘为路径引用 | 零 | DISCARDABLE（热尾窗口外） |
| 2 | LOD1 → LLM 批量摘要 | 有 | SUMMARIZABLE（非热尾轮次） |

`asyncio.Lock` 串行化防并发重入。压缩后 session.ApplyCompactionResult 替换消息列表（一步到位，保留 LOD0）。

冷卸载：原地修改 `msg.content` 为 `[archived at path]` 或 `[aged:XKB]` 占位，标记 `isAgedOut`。热尾窗口保护（keepRecentTurns 条 DISCARDABLE 不卸载）。

**AutoColdOffloadIfNeeded**：每轮用户对话前依据宽限期（coldOffloadGraceSeconds，默认 300s）判断是否冷卸载，保护 Prompt Cache 命中率。

**孤儿保护**：热尾窗口内 DISCARDABLE 所在轮次的 ASSISTANT（含 tool_calls）必须保留，否则 TOOL 消息孤儿化导致 API 400。

### 4. AfterTurnAsync

由 Agent._RunGuardedAsync 的 finally 块调用：RemoveExpiredLod3（LOD3 当轮注入次轮丢弃）+ SaveToMemory（持久化）。

## ContextMessage

Session 中存储的标准消息，带唯一 messageId 和 LOD 标记。关键字段：messageId（uuid4().int）、lodLevel、turnIndex（摘要消息为 -1）、createdAt（宽限期判断基准）、isCompacted、isAgedOut。

## 关键设计

- **ContextComponent 不存储消息**——消息唯一归属 SessionComponent。
- **增量估算**：以真实 promptTokens + 新增消息 delta。
- **LOD0 不可触碰**：任何压缩路径不修改/丢弃/摘要 RESIDENT 消息。
- **Prompt Caching**：只在 stable prefix（RESIDENT）末尾标记。
- **摘要消息 turnIndex=-1**：以 SYSTEM 消息形式存储在 messages 列表中。
