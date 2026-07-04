# LLMComponent

LLM 协议在 Agent 框架内的唯一代理层。所有 LLM 调用必须通过 LLMComponent，禁止直接持有 BaseLLM。集中管理请求参数、Token 统计、事件推送。

## 四维调用

| 维度 | 同步/异步 | 流式/非流式 |
|------|----------|------------|
| Invoke | 同步 | 非流式 |
| Stream | 同步 | 流式 |
| InvokeAsync | 异步 | 非流式 |
| StreamAsync | 异步 | 流式 |

Async 方法返回 ChatResponse（content + reasoningContent + toolCalls + usage）。

## 工具绑定

`BindTools(toolSpecs)` 原地修改 `_requestParams.tools`，之后所有调用自动带上工具。由 HarnessComponent.BuildAsync 末尾调用，一次性聚合内置工具 + Skill 工具 + MCP 工具。

## 事件推送内聚

StreamAsync 内部直接推送事件到 EventBusComponent，Agent 主循环无需自行管理缓冲区：

```
StreamAsync 内部流程:
  重置 StringIO 缓冲
  async for chunk:
    reasoningContent → EmitEvent(ThinkingDelta)
    content → EmitEvent(TextDelta)
    toolCalls → 累积
  结束 → EmitEvent(TextComplete) + ThinkingComplete
  记录 token 用量
  return ChatResponse
```

## Token 管理

- **LastPromptTokens**：最近一次 LLM 返回的 promptTokens，作为增量估算基准。
- **EstimateTokens(messages)**：估算 ContextMessage 列表总 token。
- **TotalPromptTokens / TotalCompletionTokens**：累计用量。
- 内嵌 TokenEstimator，实例级隔离。

## 关键设计

- **同一 Agent 所有 LLM 调用走同一 `_requestParams`**，BindTools 修改后立即生效。
- **OnInitialize 完成后 `_llm` 不再变化**，切模型必须重建 Agent。
- **StreamAsync 返回 ChatResponse**（非旧版 ChatMessage），含完整 reasoningContent。
- ContextCompactor 内部压缩调用也经此累加到 BaseLLM，全 Agent 一份用量账。
