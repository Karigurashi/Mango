# API 参考

## LLMManager

静态管理类，配置加载 + Provider 连接池管理。首次 `GetProvider` 时自动懒加载 `workspace/models.json`。

### 获取 Provider

| 方法 | 说明 |
|------|------|
| `GetProvider(name: str | None = None) → BaseLLM` | 按模型名获取 BaseLLM Provider，name 为空时回退 defaultModel |
| `GetConfig(name: str) → LLMModel` | 获取指定模型配置 |
| `ListModels() → list[str]` | 列出所有已注册模型名 |
| `DefaultModel() → str` | 获取默认模型名 |
| `SetDefaultModel(value: str)` | 设置默认模型名 |

### 模型管理

| 方法 | 说明 |
|------|------|
| `AddModel(model: LLMModel)` | 动态注册模型 |
| `RemoveModel(name: str)` | 移除模型 |
| `InitFromPath(jsonPath: str)` | 手动加载指定 JSON 配置，可多次调用切换 |

### 资源清理

```python
LLMManager.Close()              # 同步关闭所有连接池
await LLMManager.CloseAsync()   # 异步关闭
```

---

## BaseLLM（抽象基类）

所有 Provider 继承此基类，定义四维调用接口。

### 元信息

| 属性 | 说明 |
|------|------|
| `ProviderName → str` | Provider 标识，如 `"openai"` / `"anthropic"` / `"gemini"` |
| `ModelName → str` | 底层实际模型名，如 `"deepseek-reasoner"` |

### 四维调用

| 方法 | 返回 |
|------|------|
| `Invoke(messages, requestParams) → ChatResponse` | 同步非流式 |
| `Stream(messages, requestParams) → Iterator[ChatChunk]` | 同步流式 |
| `await InvokeAsync(messages, cancellationToken, requestParams) → ChatResponse` | 异步非流式 |
| `async for StreamAsync(messages, cancellationToken, requestParams) → ChatChunk` | 异步流式 |

### 工具绑定

```python
provider.BindTools(tools: list[ToolSpec])
```

绑定后后续调用自动携带工具定义。也可通过 `LLMRequestParams.tools` 请求级注入。

### Token 用量

| 属性/方法 | 说明 |
|-----------|------|
| `TotalUsage → TokenUsage` | 累计 Token 用量 |
| `ResetUsage()` | 重置累计 |
| `CountTokens(messages) → int` | 估算消息 token 数（字符数/4 粗略估算） |

---

## LLMRequestParams

请求参数数据类，所有调用参数均通过此对象传递（不使用 `**kwargs`）。

```python
from llm import LLMRequestParams

rp = LLMRequestParams(
    temperature=0.7,       # 采样温度 [0, 2]
    maxTokens=0,           # 最大生成 token 数，0 不限制
    enableThinking=False,   # 启用 Extended Thinking（Anthropic）
    thinkingBudget=0,       # Thinking 预算 token 数
    enableCache=True,       # 启用 KV-Cache / Prompt Caching
    extraParams=None,       # 透传额外参数（top_p 等）
    tools=None,             # 请求级工具列表
    onBeforeRequest=None,   # 请求前回调 Callable[[list[ChatMessage]], None]
    onAfterRequest=None,    # 请求后回调 Callable[[ChatResponse], None]
    onError=None,           # 异常回调 Callable[[Exception], None]
)
```

静态默认实例：`LLMRequestParams.DEFAULT`（只读使用，避免重复分配）。

---

## 职责边界

| 职责 | LLMManager | BaseLLM(BaseProvider) | LLMRequestParams |
|------|:---------:|:---------:|:---------:|
| 加载 JSON 配置 | ✓ | | |
| 创建/管理 Provider 连接池 | ✓ | | |
| 按名称分发 Provider | ✓ | | |
| Invoke/Stream 四维调用 | | ✓ | |
| 工具绑定 BindTools | | ✓ | |
| KV-Cache 开关 | | | ✓ (enableCache) |
| 请求级回调 | | | ✓ (onBefore/After/Error) |
| 请求级工具 | | | ✓ (tools) |
| Token 用量累计/重置 | | ✓ | |
| 结构化日志 | | ✓ | |

---

## 四维调用矩阵

| | 同步 | 异步 |
|---|---|---|
| **非流式** | `provider.Invoke(messages, requestParams=rp) → ChatResponse` | `await provider.InvokeAsync(messages, cancellationToken=ct, requestParams=rp) → ChatResponse` |
| **流式** | `provider.Stream(messages, requestParams=rp) → Iterator[ChatChunk]` | `async for provider.StreamAsync(messages, cancellationToken=ct, requestParams=rp) → ChatChunk` |

---

## 完整使用示例

```python
from llm import LLMManager, ChatMessage, LLMRequestParams, ToolSpec

# 获取 Provider（首次调用自动加载 workspace/models.json）
provider = LLMManager.GetProvider("deepseek-high")
defaultProvider = LLMManager.GetProvider(LLMManager.DefaultModel())

# 消息
messages = [
    ChatMessage.System("用中文回答"),
    ChatMessage.User("9.9和9.11哪个大？"),
]

# 四维调用
rp = LLMRequestParams(temperature=0.0, maxTokens=200)
resp = provider.Invoke(messages, requestParams=rp)
for chunk in provider.Stream(messages, requestParams=rp): print(chunk.content, end="")
resp = await provider.InvokeAsync(messages, requestParams=rp)
async for chunk in provider.StreamAsync(messages, requestParams=rp): print(chunk.content, end="")

# Thinking
resp = provider.Invoke(messages)
print(resp.reasoningContent)  # 思考过程
print(resp.content)           # 最终答案

# 请求级工具
tools = [ToolSpec(name="get_weather", description="查询天气", parameters={...})]
rp = LLMRequestParams(tools=tools)
resp = provider.Invoke(messages, requestParams=rp)

# 请求级回调
rp = LLMRequestParams(
    onBeforeRequest=lambda msgs: print(f"发送 {len(msgs)} 条消息"),
    onAfterRequest=lambda resp: print(f"收到 {resp.usage}"),
    onError=lambda exc: print(f"错误: {exc}"),
)
resp = provider.Invoke(messages, requestParams=rp)

# 用量
for name in LLMManager.ListModels():
    p = LLMManager.GetProvider(name)
    print(f"{name}: {p.TotalUsage.totalTokens}")
```
