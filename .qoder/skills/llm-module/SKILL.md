---
name: llm-module
description: 多模型统一调度层，封装 OpenAI/Anthropic/Gemini 官方 SDK，通过 BaseLLM 提供同步/异步、流式/非流式四维调用接口。支持 JSON 配置加载、Token 用量追踪、KV-Cache、工具绑定、请求级回调、结构化日志。使用 LLMManager 静态类自动加载，或需要在 llm/ 目录下修改 Provider、新增模型配置、排查调用错误时参考。
---

# LLM 底层调用模块

## 数据流

```
models.json  →  LLMManager  →  BaseLLM(Provider)  →  SDK  →  API
  配置           静态管理器       Provider 实例       官方 SDK
```

## 快速开始

```python
from llm import LLMManager, ChatMessage, LLMRequestParams

# 获取 Provider（首次调用自动加载 workspace/models.json）
provider = LLMManager.GetProvider("deepseek-high")     # 按名称

# 四种调用方式
rp = LLMRequestParams(temperature=0.0, maxTokens=200)
resp = provider.Invoke(messages, requestParams=rp)                        # 同步非流式
for chunk in provider.Stream(messages, requestParams=rp): ...             # 同步流式
resp = await provider.InvokeAsync(messages, requestParams=rp)             # 异步非流式
async for chunk in provider.StreamAsync(messages, requestParams=rp): ...  # 异步流式

# Thinking（DeepSeek R1 / Claude）
resp = provider.Invoke(messages)
print(resp.reasoningContent)  # 思考过程

# 请求级工具 & 回调
from llm import ToolSpec
tools = [ToolSpec(name="get_weather", description="查询天气", parameters={...})]
rp = LLMRequestParams(
    tools=tools,
    onBeforeRequest=lambda msgs: print(f"发送 {len(msgs)} 条消息"),
    onAfterRequest=lambda resp: print(f"收到 {resp.usage}"),
)
resp = provider.Invoke(messages, requestParams=rp)
```

## 关键概念

| 概念 | 说明 |
|------|------|
| **LLMManager** | 静态管理类：配置加载 + Provider 连接池管理，`GetProvider` 分发 BaseLLM |
| **BaseLLM** | 抽象基类，定义 Invoke/Stream/InvokeAsync/StreamAsync 四维接口 |
| **BaseProvider** | 继承 BaseLLM 的 Provider 基类，提供回调/用量/日志/异常转换 |
| **LLMRequestParams** | 请求参数数据类：温度、工具、回调、Thinking、Cache 均通过此对象传递 |
| **Protocol 层** | 每个厂商独立的消息/工具格式转换，解耦 Provider 与 API 差异 |

## 文件引用

| 文档 | 内容 |
|------|------|
| [config-guide.md](config-guide.md) | models.json 配置格式、字段说明、Provider 推断规则 |
| [api-reference.md](api-reference.md) | LLMManager / BaseLLM / LLMRequestParams 完整 API、职责边界表、四维矩阵 |
| [architecture.md](architecture.md) | 文件结构、分层架构图、核心类职责表、结构化日志 |
| [provider-guide.md](provider-guide.md) | Thinking 模式、KV-Cache、工具绑定、消息归一化、请求级回调、扩展新 Provider |
