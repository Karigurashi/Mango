# LLMComponent LLM 能力封装

> 源码：[`agent/component/llm/llmComponent.py`](../../../agent/component/llm/llmComponent.py)

LLMComponent 是 LLM 协议在 Agent 框架内的**唯一代理层**。其他组件（包括 Agent 主循环、ContextCompactor、MemoryCompiler）想调用 LLM，**都必须通过 LLMComponent**，禁止直接持有 `BaseLLM` 引用。这样做的目的：

* **请求参数集中管理**：tool spec / temperature / maxTokens / 模型名等通过 `_requestParams` 一处配置；
* **Token 统计聚合**：所有调用经同一 `_tokenEstimator` 累加，便于 budget 控制；
* **替换底层 Provider 不影响业务**：DataComponent 持有的 `BaseLLM` 实现可换 OpenAI / Claude / 国产模型，调用方零修改。

## 1 字段

```text
LLMComponent
  ├─ _llm:             BaseLLM             # 来自 DataComponent
  ├─ _requestParams:   LLMRequestParams    # tools / temperature / maxTokens / modelName
  └─ _tokenEstimator:  TokenEstimator      # 实例级，避免跨 Agent 累加
```

> **TokenEstimator 实例隔离**：每个 LLMComponent 创建自己的 `TokenEstimator`，多 Agent 并发跑时统计互不污染。

## 2 OnInitialize 依赖注入

```text
OnInitialize(agent)
  ├─ data = agent.GetComponent(DataComponent)
  ├─ self._llm = data.Llm
  ├─ self._tokenEstimator = TokenEstimator()
  ├─ self._requestParams = LLMRequestParams(
  │       modelName   = data.Config.modelName,
  │       temperature = data.Config.temperature,
  │       maxTokens   = data.Config.maxTokens,
  │   )
  └─ self._llm.Configure(modelName=data.Config.modelName)
```

> `Configure` 只在 OnInitialize 调一次；运行时切模型必须重新构造 Agent。

## 3 工具绑定 `BindTools`

```text
BindTools(toolSpecs: list[dict]) -> None
  └─ self._requestParams.tools = toolSpecs   # 原地替换
```

* `toolSpecs` 由 ToolComponent 通过 `BaseTool.ToToolSpec()` 生成；
* HarnessComponent 在 `BuildAsync` 末尾调用 `BindTools`，把"内置 + Skill 加载工具 + MCP 工具"统一注册到 LLM；
* **原地修改 `_requestParams`**：所有后续调用自动带上工具，无需每次重传。

## 4 四维调用代理

| 调用方法 | 同步/异步 | 流式 | 返回 |
|---------|----------|------|------|
| `Invoke(messages, **kw) -> ChatMessage` | 同步 | 否 | 完整 ChatMessage |
| `Stream(messages, **kw) -> Iterator[delta]` | 同步 | 是 | 增量 chunk |
| `InvokeAsync(messages, **kw) -> ChatMessage` | 异步 | 否 | 完整 ChatMessage |
| `StreamAsync(messages, **kw) -> AsyncIterator[delta]` | 异步 | 是 | 增量 chunk |

```text
四个方法的统一前置流程：
  ├─ messages = self._NormalizeMessages(messages)   # 见 §5
  ├─ params   = kw.get("requestParams") or self._requestParams
  ├─ self._llm.<对应原生方法>(messages, requestParams=params)
  └─ self._tokenEstimator.RecordUsage(usage)        # 后置统计
```

## 5 消息归一化

LLM 调用方传入的 messages 形态多样，由三个静态/实例方法统一为 `list[ChatMessage]`：

| 输入 | 转换器 |
|------|--------|
| `str`（直接 user query） | `FromStr` → 单条 `ChatMessage.User(query)` |
| `list[dict]`（OpenAI 风格 dict） | `FromDicts` → 按 role 字段构造 ChatMessage |
| `list[ChatMessage]` | 透传 |

> 这一层归一化让 ContextComponent / Memory / 测试代码都能用最方便的形态调用，**调用方不必关心底层 Provider 的 schema**。

## 6 用量追踪

```text
GetUsage() -> dict
    返回累计 {inputTokens, outputTokens, totalTokens, callCount}

ResetUsage() -> None
    清零 _tokenEstimator 计数器（用于按 Run 切片观测）
```

* Agent 在 `RunStart` 调 `ResetUsage`，`RunEnd` 调 `GetUsage` 写入 `LoggingComponent.LogRunEnd`；
* MemoryCompiler / ContextCompactor 内部调用同样累加到这里——**全 Agent 一份用量账**。

## 7 与其他组件的关系

| 角色 | 用途 |
|------|------|
| ContextComponent | `LLMComponent.InvokeAsync` 用作压缩 LLM（ContextCompactor 持有的是 BaseLLM 引用，**直接来自 DataComponent**——这是历史决策，未来可统一到 LLMComponent） |
| Agent 主循环 | `StreamAsync` 实现 ReAct Think 阶段 |
| MemoryComponent | `InvokeAsync` 编译会话摘要 |
| Skill / Rule | 自身不调 LLM，仅注入 system prompt |

## 8 关键不变式

1. **同一 Agent 实例的所有 LLM 调用走同一 `_requestParams` 引用**——`BindTools` 修改后立即对所有调用生效。
2. **TokenEstimator 实例级隔离**：跨 Agent 不串号。
3. **OnInitialize 完成后 `_llm` 不再变化**；切模型必须重建 Agent。
4. **同步桥接 (`Invoke / Stream`) 内部不再 `asyncio.run`**——直接走 BaseLLM 的同步路径，保证 FastAPI / Jupyter 等已运行 loop 的环境调用安全。
