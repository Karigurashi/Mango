# API 参考

## LLMManager

### 初始化

```python
manager = LLMManager("worksapce/models.json")
```

### 获取客户端

| 方法 | 说明 |
|------|------|
| `GetClient(name: str) → LLMClient` | 按模型名获取 Client，共享底层 Provider |
| `GetClientByTier(tier: ETier) → LLMClient` | 按档位获取 Client |

### 模型管理

| 方法/属性 | 说明 |
|-----------|------|
| `ListModels() → list[str]` | 列出所有已注册模型名 |
| `DefaultModel → str` | 默认模型名（可读写） |
| `GetConfig(name) → LLMConfig` | 获取指定模型配置 |
| `AddModel(config, providerType)` | 动态注册模型 |
| `RemoveModel(name)` | 移除模型 |
| `ReloadConfig(path)` | 重新加载配置 |

### 资源清理

```python
manager.Close()              # 同步关闭所有连接池
await manager.CloseAsync()   # 异步关闭
```

---

## LLMClient

### 元信息

| 属性 | 说明 |
|------|------|
| `ModelName → str` | 底层实际模型名，如 `"deepseek-reasoner"` |
| `ProviderName → str` | 厂商名：`"openai"` / `"anthropic"` / `"gemini"` |
| `Tier → ETier` | 模型档位 |

### 四维调用

| 方法 | 返回 |
|------|------|
| `Invoke(messages, temperature, maxTokens, **kwargs) → ChatResponse` | 同步非流式 |
| `Stream(messages, temperature, maxTokens, **kwargs) → Iterator[ChatChunk]` | 同步流式 |
| `await InvokeAsync(messages, temperature, maxTokens, **kwargs) → ChatResponse` | 异步非流式 |
| `async for StreamAsync(messages, temperature, maxTokens, **kwargs) → ChatChunk` | 异步流式 |

### 消息输入

支持三级自动归一化：

```python
client.Invoke("你好")                                # str → [ChatMessage.User("你好")]
client.Invoke([{"role": "user", "content": "hi"}])   # dict → ChatMessage
client.Invoke([ChatMessage.User("hi")])               # 直接透传
```

### 工具绑定

```python
client.BindTools(tools: list[ToolSpec])
```

绑定后后续 `Invoke/Stream` 自动携带工具定义。

### KV-Cache

```python
client.EnableCache(True)   # 开启 Anthropic Prompt Caching
client.EnableCache(False)  # 关闭
```

### 用量查询

```python
client.GetUsage()    # → TokenUsage
client.ResetUsage()  # 重置累计
```

---

## 职责边界

| 职责 | LLMManager | LLMClient |
|------|:---------:|:---------:|
| 加载 JSON 配置 | ✓ | |
| 创建/管理 Provider 连接池 | ✓ | |
| 按名称/档位分发 Client | ✓ | |
| Invoke/Stream 四维调用 | | ✓ |
| 消息归一化(str/dict/ChatMessage) | | ✓ |
| 工具绑定 BindTools | | ✓ |
| KV-Cache 开关 EnableCache | | ✓ |
| Token 用量查询/重置 | | ✓ |
| 回调钩子 | (Provider 层) | |

---

## 四维调用矩阵

| | 同步 | 异步 |
|---|---|---|
| **非流式** | `client.Invoke(messages) → ChatResponse` | `await client.InvokeAsync(messages) → ChatResponse` |
| **流式** | `client.Stream(messages) → Iterator[ChatChunk]` | `async for client.StreamAsync(messages) → ChatChunk` |

---

## 回调钩子

通过 Client 访问底层 Provider 注册：

```python
client = manager.GetClient("deepseek-high")

def before(msgs): print(f"发送 {len(msgs)} 条消息")
def after(resp): print(f"收到 {resp.usage}")
def onError(exc): print(f"错误: {exc}")

client._provider.OnBeforeRequest(before)
client._provider.OnAfterRequest(after)
client._provider.OnError(onError)
```

---

## 完整使用示例

```python
from llm import LLMManager, ChatMessage, ETier

manager = LLMManager("worksapce/models.json")

# 获取客户端
client = manager.GetClient("deepseek-high")
high = manager.GetClientByTier(ETier.HIGH)
defaultClient = manager.GetClient(manager.DefaultModel)

# 消息（三种写法等价）
messages = [
    ChatMessage.System("用中文回答"),
    ChatMessage.User("9.9和9.11哪个大？"),
]

# 四维调用
resp = client.Invoke(messages, temperature=0.0, maxTokens=200)
for chunk in client.Stream(messages): print(chunk.content, end="")
resp = await client.InvokeAsync(messages)
async for chunk in client.StreamAsync(messages): print(chunk.content, end="")

# Thinking
resp = high.Invoke(messages)
print(resp.reasoningContent)  # 思考过程
print(resp.content)           # 最终答案

# 工具
from llm import ToolSpec
tools = [ToolSpec(name="get_weather", description="查询天气", parameters={...})]
client.BindTools(tools)

# 用量
for name in manager.ListModels():
    c = manager.GetClient(name)
    print(f"{name}: {c.GetUsage().totalTokens}")
```
