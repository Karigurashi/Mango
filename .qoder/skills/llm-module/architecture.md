# 架构与文件结构

## 数据流

```
models.json  →  LLMManager  →  BaseLLM(Provider)  →  SDK  →  大模型 API
  配置           静态管理器       Provider 实例       官方 SDK     DeepSeek/GPT/Claude/Gemini
```

LLMManager 读取 JSON 配置 → 工厂创建 Provider（OpenAI/Anthropic/Gemini）→ 通过 `GetProvider(name)` 分发 BaseLLM → BaseLLM 提供 `Invoke/Stream/InvokeAsync/StreamAsync` 四维调用。调用参数通过 `LLMRequestParams` 传递，包含温度、工具、回调、Thinking、Cache 等全部控制项。

## 文件结构

```
llm/
├── __init__.py                  # 统一导出
├── baseLLM.py                   # 抽象基类 BaseLLM（4 个抽象方法 + BindTools + Token 用量）
├── llmConfig.py                 # 配置类 LLMConfig（根）+ LLMModel（子条目），从 JSON dict 反序列化
├── llmManager.py                # 静态管理类 LLMManager（配置加载、Provider 连接池、GetProvider 分发）
├── llmRequestParams.py          # 请求参数数据类 LLMRequestParams（温度/工具/回调/Thinking/Cache）
├── tokenEstimator.py            # Token 估算器 TokenEstimator（tiktoken 优先，降级 chars/4，实例级隔离）
├── provider/
│   ├── __init__.py              # Provider 层统一导出
│   ├── baseProvider.py          # 基类 BaseProvider（回调/用量/日志/异常转换/超时包装/取消检查）
│   ├── chatMessage.py           # 数据模型（ChatMessage/ChatResponse/ChatChunk/TokenUsage/ToolSpec/ToolCall）
│   ├── openai/
│   │   ├── __init__.py
│   │   ├── openaiProvider.py    # OpenAI SDK 封装（同步+异步，含 reasoning_content 提取）
│   │   └── openaiProtocol.py    # OpenAI 协议层（消息/工具格式转换、参数构建、ToolCall 解析）
│   ├── anthropic/
│   │   ├── __init__.py
│   │   ├── anthropicProvider.py # Anthropic SDK 封装（含 Extended Thinking、KV-Cache）
│   │   └── anthropicProtocol.py # Anthropic 协议层（system 分离、工具回合编码、CacheControl、Thinking 配置）
│   └── gemini/
│       ├── __init__.py
│       ├── geminiProvider.py    # Gemini SDK 封装（懒加载 genai.Client）
│       └── geminiProtocol.py    # Gemini 协议层（消息/工具格式转换、system_instruction 提取）
common/
├── logger.py                    # Logger 日志类（Info/Warning/Error/Debug）
├── llmError.py                  # LLMError 自定义异常（携带 provider/model/statusCode/responseBody）
└── const.py                     # ERole 枚举（SYSTEM/USER/ASSISTANT/TOOL）、ERoad 路径常量
agent/component/llm/
└── llmComponent.py              # LLMComponent（IComponent 封装，消息归一化、工具绑定、四维调用代理）
```

## 分层架构

```
调用方 (Agent / LLMComponent)
  │
  ▼
LLMManager                               ← 静态管理类：配置加载、Provider 连接池、GetProvider 分发
  │  GetProvider(name) / ListModels() / DefaultModel()
  ▼
BaseLLM (抽象基类)                        ← 四维抽象方法定义 + BindTools + TotalUsage
  │
  ▼
BaseProvider (基类)                       ← 回调钩子 / Token 累计 / 结构化日志 / LLMError 转换
  │  请求级回调来自 LLMRequestParams
  │
  ├── OpenAIProvider                      ← openai.OpenAI / openai.AsyncOpenAI
  │     └── OpenAIProtocol                ← FormatMessages / FormatTools / ParseToolCalls / BuildRequestParams
  │
  ├── AnthropicProvider                   ← anthropic.Anthropic / anthropic.AsyncAnthropic
  │     └── AnthropicProtocol             ← FormatMessages(含 system 分离+工具回合编码) / BuildCacheControl / BuildRequestParams
  │
  └── GeminiProvider                      ← google.genai.Client（懒加载）
        └── GeminiProtocol                ← FormatMessages / FormatTools / GetSystemInstruction / BuildRequestParams
```

## 核心类职责

| 文件 | 类 | 职责 |
|------|-----|------|
| `llmManager.py` | `LLMManager` | 静态管理类：加载 JSON 配置、工厂创建 Provider、管理共享连接池、按名称分发 BaseLLM |
| `baseLLM.py` | `BaseLLM` | 抽象基类：定义 `Invoke/Stream/InvokeAsync/StreamAsync` 四维接口 + `BindTools/TotalUsage/ResetUsage` |
| `llmRequestParams.py` | `LLMRequestParams` | 请求参数数据类：temperature/maxTokens/enableThinking/thinkingBudget/enableCache/tools/回调/extraParams |
| `llmConfig.py` | `LLMConfig` | models.json 根类型，包含 models 列表 + defaultModel |
| `llmConfig.py` | `LLMModel` | 单一模型连接配置（name/url/apiKey/provider/modelName/timeout/maxRetries/streamTimeout/thinkingBudget） |
| `provider/baseProvider.py` | `BaseProvider` | 基类：Token 用量累计、`_LogSuccess/_LogError` 结构化日志、`_RaiseLLMError` 异常转换、`_InvokeWithTimeoutAsync` 超时包装、`_CheckCancellation` 取消检查 |
| `provider/chatMessage.py` | `ChatMessage` | 消息（role + content + toolCalls + toolCallId + cacheControl），含 `System/User/Assistant/Tool` 工厂方法，协议缓存 `ToOpenAI/ToAnthropic` |
| `provider/chatMessage.py` | `ChatResponse` | 非流式完整返回（content + reasoningContent + usage + finishReason + toolCalls + rawResponse） |
| `provider/chatMessage.py` | `ChatChunk` | 流式增量产出，`isEmpty` 属性过滤空块 |
| `provider/chatMessage.py` | `TokenUsage` | promptTokens/completionTokens/totalTokens，支持 `+` 累加 |
| `provider/chatMessage.py` | `ToolSpec` | 工具定义（name + description + parameters JSON Schema） |
| `provider/chatMessage.py` | `ToolCall` | 工具调用结果（id + name + arguments） |
| `tokenEstimator.py` | `TokenEstimator` | Token 估算器，tiktoken 优先降级 chars/4，纯实例模式（每个 Agent 隔离），支持消息级缓存消除 O(n²) |
| `common/llmError.py` | `LLMError` | 异常携带 provider/model/statusCode/responseBody 上下文 |
| `common/logger.py` | `Logger` | 日志类，`Logger.Info("msg")` 直接调用 |
| `llmComponent.py` | `LLMComponent` | Agent IComponent 封装：持有 BaseLLM、消息归一化(FromStr/FromDicts/FromChatMessages)、工具绑定、四维调用代理、独立 TokenEstimator |

## 结构化日志

```
rid=6f9d0d58 Invoke openai/deepseek-reasoner dur=1250ms tokens_in=21 tokens_out=55
rid=53dcafed Stream openai/deepseek-chat dur=718ms tokens_in=21 tokens_out=5
```

每个请求自动分配 8 位 `rid`（UUID 前缀），包含：方法名、provider/模型、耗时、输入/输出 token 数。
