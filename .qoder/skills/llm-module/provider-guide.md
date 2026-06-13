# Provider 功能指南

## Thinking 模式

| 模型 | Thinking 方式 | 参数 |
|------|--------------|------|
| DeepSeek Reasoner (R1) | 模型内建，始终输出 `reasoning_content` | 无需额外参数 |
| Claude 3.5+ | `thinking: {type: "enabled", budget_tokens: N}` | `LLMRequestParams(enableThinking=True, thinkingBudget=8000)` |
| DeepSeek Chat (V3) | 不支持 thinking | - |
| Gemini | 不支持 thinking | - |

```python
from llm import LLMManager, ChatMessage, LLMRequestParams

# DeepSeek Reasoner 自动输出
provider = LLMManager.GetProvider("deepseek-high")
resp = provider.Invoke(messages)
print(resp.reasoningContent)  # 思考过程
print(resp.content)           # 最终答案

# Anthropic Extended Thinking 需通过 LLMRequestParams 显式传参
claude = LLMManager.GetProvider("claude-3")
rp = LLMRequestParams(enableThinking=True, thinkingBudget=8000)
resp = claude.Invoke(messages, requestParams=rp)
```

### 实现细节

- OpenAIProvider：`reasoning_content` 通过 Pydantic `model_extra` 提取，仅 DeepSeek Reasoner 有值
- AnthropicProvider：`enableThinking=True` 时注入 `thinking` 块，`content` 中分离 text/thinking
- Anthropic thinkingBudget 回退逻辑：`rp.thinkingBudget or self._thinkingBudget`，优先请求级，回退到模型配置级

## KV-Cache（Anthropic Prompt Caching）

```python
rp = LLMRequestParams(enableCache=True)
resp = provider.Invoke(messages, requestParams=rp)
```

`enableCache` 默认为 `True`。AnthropicProtocol 对标记了 `cacheControl=True` 的消息注入 `{"type": "ephemeral"}` 的 `cache_control`。

## 工具绑定

### 方式一：请求级工具（推荐）

```python
from llm import ToolSpec, LLMRequestParams

tools = [
    ToolSpec(
        name="get_weather",
        description="查询城市天气",
        parameters={
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "城市名"}
            },
            "required": ["city"]
        }
    )
]
rp = LLMRequestParams(tools=tools)
resp = provider.Invoke(messages, requestParams=rp)
```

### 方式二：Provider 级工具绑定

```python
provider.BindTools(tools)
resp = provider.Invoke(messages)  # 自动携带工具定义
```

### 方式三：LLMComponent 封装（Agent 层）

```python
llmComp = agent.GetComponent(LLMComponent)
llmComp.BindTools(tools)
resp = llmComp.Invoke(messages)  # 自动携带工具定义
```

各厂商 Protocol 负责将 `ToolSpec` 转换为对应 API 格式：
- OpenAI：`{"type": "function", "function": {...}}`
- Anthropic：`{"name": ..., "input_schema": ...}` 格式
- Gemini：`{"function_declarations": [...]}` 格式

## 请求级回调

通过 `LLMRequestParams` 注册请求级回调，每次调用可不同：

```python
def before(msgs): print(f"发送 {len(msgs)} 条消息")
def after(resp): print(f"收到 {resp.usage}")
def onError(exc): print(f"错误: {exc}")

rp = LLMRequestParams(
    onBeforeRequest=before,
    onAfterRequest=after,
    onError=onError,
)
resp = provider.Invoke(messages, requestParams=rp)
```

- `onBeforeRequest`：请求发送前，传入归一化后的 `list[ChatMessage]`
- `onAfterRequest`：请求成功后，传入完整 `ChatResponse`
- `onError`：异常发生时，传入原始异常（在 `_RaiseLLMError` 转换前调用）

## 消息归一化

LLMComponent 提供三级消息归一化（三个明确签名，禁止 isinstance 分支）：

```python
from agent.component.llm.llmComponent import LLMComponent

llmComp = agent.GetComponent(LLMComponent)
llmComp.Invoke(messages=LLMComponent.FromStr("你好"))                      # str → [ChatMessage.User("你好")]
llmComp.Invoke(messages=LLMComponent.FromDicts([{"role": "user", "content": "hi"}]))  # dict → ChatMessage
llmComp.Invoke(messages=LLMComponent.FromChatMessages([ChatMessage.User("hi")]))       # 直接透传
```

注意：BaseLLM / BaseProvider 层不接受 str/dict 输入，消息归一化仅在 LLMComponent 层处理。

## 超时与取消

### 双重超时保护

- SDK 内置 timeout：控制单次 HTTP 请求超时（通过 `LLMModel.timeout` 配置）
- 框架层 timeout：`_InvokeWithTimeoutAsync` 用 `asyncio.wait_for` 包装，控制整个调用生命周期（含重试时间），默认取 `LLMModel.timeout`

### CancellationToken

异步调用支持通过 CancellationToken 在 chunk 间取消：

```python
from common.cancellationToken import CancellationToken

ct = CancellationToken()
# 在其他协程中: ct.Cancel()

async for chunk in provider.StreamAsync(messages, cancellationToken=ct, requestParams=rp):
    print(chunk.content, end="")
```

取消时：
- StreamAsync 在下一个 chunk 检查点跳出循环
- 主动关闭底层连接（OpenAI: `stream.close()`，Anthropic: `async with` 自动关闭，Gemini: `stream.aclose()`）
- 记录 `CANCELLED by token` 日志

## 扩展新 Provider

1. 在 `llm/provider/` 下新建厂商子目录（如 `llm/provider/xxx/`）
2. 新建 `xxxProtocol.py`：实现 `FormatMessages` / `FormatTools` / `BuildRequestParams` 等协议方法
3. 新建 `xxxProvider.py`：继承 `BaseProvider`，实现 `Invoke/Stream/InvokeAsync/StreamAsync`
4. 覆盖 `ProviderName` 属性
5. 在 `llmManager.py` 的 `_CreateProvider` 添加分支
6. 在 `llm/provider/xxx/__init__.py` 和 `llm/provider/__init__.py` 导出

### Protocol 接口约定

```python
class XxxProtocol:
    @staticmethod
    def FormatMessages(messages: list[ChatMessage], **kwargs) -> list[dict]:
        """将 ChatMessage 列表转换为厂商原生消息格式。"""
        ...

    @staticmethod
    def FormatTools(tools: list[ToolSpec]) -> list[dict]:
        """将 ToolSpec 列表转换为厂商原生工具格式。"""
        ...

    def BuildRequestParams(
        self,
        messages: list[ChatMessage],
        requestParams: LLMRequestParams,
        stream: bool,
        tools: list[ToolSpec] | None = None,
        modelName: str = "",
    ) -> dict:
        """构建厂商原生 API 请求参数。"""
        ...
```
