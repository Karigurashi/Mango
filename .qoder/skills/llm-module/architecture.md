# 架构与文件结构

## 数据流

```
models.json  →  LLMManager  →  LLMClient  →  Provider(SDK)  →  大模型 API
  配置           管理器          客户端         官方 SDK           DeepSeek/GPT/Claude/Gemini
```

LLMManager 读取 JSON 配置 → 工厂创建 Provider（OpenAI/Anthropic/Gemini）→ 通过 `GetClient(name)` 或 `GetClientByTier(tier)` 分发 LLMClient → LLMClient 提供 `Invoke/Stream/InvokeAsync/StreamAsync` 四维调用。

## 文件结构

```
llm/
├── __init__.py                  # 统一导出
├── baseLLM.py                   # 抽象接口（4 个抽象方法）
├── eTier.py                     # 档位枚举 ETier(HIGH/MID/LOW)
├── llmClient.py                 # 用户端模型对象（Invoke/Stream/BindTools/EnableCache）
├── llmConfig.py                 # 配置类（从 JSON dict 反序列化，含 tier 字段）
├── llmManager.py                # 调度管理器（配置加载、Provider 连接池、Client 分发）
├── provider/
│   ├── __init__.py              # Provider 层统一导出
│   ├── baseProvider.py          # 基类 BaseProvider（回调/用量/日志/异常转换）
│   ├── chatMessage.py           # 数据模型（ChatMessage/ChatResponse/ChatChunk/TokenUsage/ToolSpec/ToolCall）
│   ├── openai/
│   │   ├── __init__.py
│   │   ├── openaiProvider.py    # OpenAI SDK 封装（同步+异步）
│   │   └── openaiProtocol.py    # OpenAI 协议层（消息/工具格式转换）
│   ├── anthropic/
│   │   ├── __init__.py
│   │   ├── anthropicProvider.py # Anthropic SDK 封装（含 Extended Thinking）
│   │   └── anthropicProtocol.py # Anthropic 协议层（system 消息分离、CacheControl）
│   └── gemini/
│       ├── __init__.py
│       ├── geminiProvider.py    # Gemini SDK 封装（懒加载）
│       └── geminiProtocol.py    # Gemini 协议层（消息/工具格式转换）
common/
├── logger.py                    # G_Logger 全局单例（Info/Warning/Error/Debug）
└── llmError.py                  # 自定义异常（携带 provider/model/statusCode/responseBody）
```

## 分层架构

```
调用方 (Agent / Blueprint)
  │
  ▼
LLMManager                               ← 配置加载、Provider 连接池管理
  │  GetClient(name) / GetClientByTier(tier)
  ▼
LLMClient                                ← 用户端统一入口
  │  Invoke / Stream / InvokeAsync / StreamAsync
  │  BindTools / EnableCache / GetUsage / ResetUsage
  │  消息归一化: str → list[dict] → list[ChatMessage]
  ▼
BaseLLM (抽象接口)                        ← 四维抽象方法定义
  │
  ▼
BaseProvider (基类)                       ← 回调钩子 / Token 累计 / 结构化日志 / LLMError 转换
  │
  ├── OpenAIProvider                      ← openai.OpenAI / openai.AsyncOpenAI
  │     └── OpenAIProtocol                ← FormatMessages / FormatTools / ParseToolCalls
  │
  ├── AnthropicProvider                   ← anthropic.Anthropic / anthropic.AsyncAnthropic
  │     └── AnthropicProtocol             ← FormatMessages(含 system 分离) / BuildCacheControl
  │
  └── GeminiProvider                      ← google.genai (懒加载)
        └── GeminiProtocol                ← FormatMessages / FormatTools
```

## 核心类职责

| 文件 | 类 | 职责 |
|------|-----|------|
| `llmManager.py` | `LLMManager` | 加载 JSON 配置、工厂创建 Provider、管理共享连接池、按名称/档位分发 LLMClient |
| `llmClient.py` | `LLMClient` | **用户端统一入口**：四维调用、消息三级归一化(str/dict/ChatMessage)、工具绑定、KV-Cache 开关、用量查询 |
| `eTier.py` | `ETier` | 模型能力档位枚举：HIGH(复杂推理) / MID(日常对话) / LOW(轻量任务) |
| `baseLLM.py` | `BaseLLM` | 定义 `Invoke/Stream/InvokeAsync/StreamAsync` 四维抽象接口 |
| `provider/baseProvider.py` | `BaseProvider` | 基类：回调钩子注册、Token 用量累计、`_LogSuccess/_LogError` 结构化日志、异常统一转换为 `LLMError` |
| `provider/chatMessage.py` | `ChatMessage` | 消息（role + content + toolCalls + toolCallId + cacheControl），含 `System/User/Assistant/Tool` 工厂方法 |
| `provider/chatMessage.py` | `ChatResponse` | 非流式完整返回（content + reasoningContent + usage + finishReason + model） |
| `provider/chatMessage.py` | `ChatChunk` | 流式增量产出，`isEmpty` 属性过滤空块 |
| `provider/chatMessage.py` | `TokenUsage` | promptTokens/completionTokens/totalTokens，支持 `+` 累加 |
| `provider/chatMessage.py` | `ToolSpec` | 工具定义（name + description + parameters JSON Schema） |
| `provider/chatMessage.py` | `ToolCall` | 工具调用结果（id + name + arguments） |
| `llmConfig.py` | `LLMConfig` | 连接配置（含 tier 字段），`FromDict(data)` 从 JSON 反序列化 |
| `common/llmError.py` | `LLMError` | 异常携带 provider/model/statusCode/responseBody 上下文 |
| `common/logger.py` | `G_Logger` | 全局日志单例，`G_Logger.Info("msg")` 直接调用 |

## 结构化日志

```
rid=6f9d0d58 Invoke openai/deepseek-reasoner dur=1250ms tokens_in=21 tokens_out=55
rid=53dcafed Stream openai/deepseek-chat dur=718ms tokens_in=21 tokens_out=5
```

每个请求自动分配 8 位 `rid`（UUID 前缀），包含：方法名、provider/模型、耗时、输入/输出 token 数。
