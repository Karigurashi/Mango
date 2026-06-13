---
name: llm-module
description: 多模型统一调度层，封装 OpenAI/Anthropic/Gemini 官方 SDK，通过 LLMClient 提供同步/异步、流式/非流式四维调用接口。支持 JSON 配置加载、三档位(ETier)调度、Token 用量追踪、KV-Cache、工具绑定、结构化日志。使用 LLMManager 时自动加载，或需要在 llm/ 目录下修改 Provider、新增模型配置、排查调用错误时参考。
---

# LLM 底层调用模块

## 数据流

```
models.json  →  LLMManager  →  LLMClient  →  Provider(SDK)  →  API
  配置           管理器          客户端         官方 SDK
```

## 快速开始

```python
from llm import LLMManager, ChatMessage, ETier

manager = LLMManager("worksapce/models.json")

# 获取客户端
client = manager.GetClient("deepseek-high")        # 按名称
high   = manager.GetClientByTier(ETier.HIGH)       # 按档位

# 四种调用方式
resp = client.Invoke("你好")                        # 同步非流式
for chunk in client.Stream(messages): ...           # 同步流式
resp = await client.InvokeAsync(messages)           # 异步非流式
async for chunk in client.StreamAsync(messages): ... # 异步流式

# Thinking（DeepSeek R1 / Claude）
resp = high.Invoke(messages)
print(resp.reasoningContent)  # 思考过程

# 工具 & Cache
client.BindTools(tools)
client.EnableCache(True)
```

## 关键概念

| 概念 | 说明 |
|------|------|
| **LLMManager** | 配置加载 + Provider 连接池管理，不直接调用模型 |
| **LLMClient** | 用户端唯一入口，提供 Invoke/Stream/BindTools/EnableCache |
| **ETier** | HIGH/MID/LOW 三档位，`GetClientByTier` 按能力调度 |
| **Protocol 层** | 每个厂商独立的消息/工具格式转换，解耦 Provider 与 API 差异 |

## 文件引用

| 文档 | 内容 |
|------|------|
| [config-guide.md](config-guide.md) | models.json 配置格式、字段说明、Provider 推断规则 |
| [api-reference.md](api-reference.md) | LLMManager / LLMClient 完整 API、职责边界表、四维矩阵、完整示例 |
| [architecture.md](architecture.md) | 文件结构、分层架构图、核心类职责表、结构化日志 |
| [provider-guide.md](provider-guide.md) | 三档调度、Thinking 模式、KV-Cache、工具绑定、消息归一化、扩展新 Provider |
