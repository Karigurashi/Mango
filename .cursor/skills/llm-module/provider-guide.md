# Provider 功能指南

## 三档调度

```python
from llm import LLMManager, ETier

manager = LLMManager("worksapce/models.json")

high = manager.GetClientByTier(ETier.HIGH)   # deepseek-reasoner，复杂推理
mid  = manager.GetClientByTier(ETier.MID)    # deepseek-chat，日常对话
low  = manager.GetClientByTier(ETier.LOW)    # deepseek-chat，轻量分类/摘要

# 档位信息
client.Tier           # ETier.HIGH
client.ModelName      # 'deepseek-reasoner'
client.ProviderName   # 'openai'
```

## Thinking 模式

| 模型 | Thinking 方式 | 参数 |
|------|--------------|------|
| DeepSeek Reasoner (R1) | 模型内建，始终输出 `reasoning_content` | 无需额外参数 |
| Claude 3.5+ | `thinking: {type: "enabled", budget_tokens: N}` | `enableThinking=True, thinkingBudget=8000` |
| DeepSeek Chat (V3) | 不支持 thinking | - |
| Gemini | 不支持 thinking | - |

```python
# DeepSeek Reasoner 自动输出
resp = high.Invoke(messages)
print(resp.reasoningContent)  # 思考过程
print(resp.content)           # 最终答案

# Anthropic Extended Thinking 需显式传参
claude = manager.GetClient("claude-3")
resp = claude.Invoke(messages, enableThinking=True, thinkingBudget=8000)
```

### 实现细节

- OpenAIProvider：`reasoning_content` 通过 Pydantic `model_extra` 提取，仅 DeepSeek Reasoner 有值
- AnthropicProvider：`enableThinking=True` 时注入 `thinking` 块，`content` 中分离 text/thinking
- 内部参数 `enableThinking`/`thinkingBudget` 在 Provider 层 `pop` 剥离，不会透传到 API

## KV-Cache（Anthropic Prompt Caching）

```python
client.EnableCache(True)
resp = client.Invoke(messages)    # 自动为消息注入 cache_control
client.EnableCache(False)
```

开启后 LLMClient 自动传 `enableCache=True` 给 Provider。AnthropicProtocol 对最后一条消息注入 `{"type": "ephemeral"}` 的 `cache_control`。

## 工具绑定

```python
from llm import ToolSpec

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
client.BindTools(tools)
resp = client.Invoke("北京今天天气怎么样？")
# resp.content 中可能包含 ToolCall
```

各厂商 Protocol 负责将 `ToolSpec` 转换为对应 API 格式：
- OpenAI：`{"type": "function", "function": {...}}`
- Anthropic：`{"type": "tool_use", ...}` 格式
- Gemini：`google.genai.types.Tool` 格式

## 消息归一化

LLMClient 自动将三种消息输入统一为 `list[ChatMessage]`：

```python
client.Invoke("你好")                                # str → [ChatMessage.User("你好")]
client.Invoke([{"role": "user", "content": "hi"}])   # dict → ChatMessage
client.Invoke([ChatMessage.User("hi")])               # 直接透传
```

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

    @staticmethod
    def BuildRequestParams(self, messages, temperature, maxTokens, stream, tools, **kwargs) -> dict:
        """构建厂商原生 API 请求参数。"""
        ...
```
