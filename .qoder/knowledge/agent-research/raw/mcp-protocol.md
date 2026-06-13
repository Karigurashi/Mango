# MCP（Model Context Protocol）协议

来源: 官方文档, DevStarsJ 2026 完整指南, ResearchGate 学术论文

## 概述

Anthropic 于 2024 年末发布，2025 年成为跨厂商开放标准，2026 年已成为 AI Agent 集成的事实标准。类比 USB 标准化外设连接，MCP 标准化 AI 模型与外部世界的交互。

## 核心概念

| 概念 | 描述 |
|------|------|
| MCP Host | LLM 应用（Claude Desktop、VS Code、自定义应用） |
| MCP Client | Host 内的协议客户端，与 Server 建立 1:1 连接 |
| MCP Server | 暴露资源、工具和提示词的轻量服务 |
| Transport | 通信通道（stdio、SSE、WebSocket） |

## 三大原语（Primitives）

### 1. Resources（资源）
只读数据源，LLM 可访问。
```
{ uri, name, mimeType }
```

### 2. Tools（工具）
LLM 可调用的函数。
```
{ name, description, inputSchema }
```

### 3. Prompts（提示词模板）
可复用的提示词，Host 可渲染。
```
{ name, description, arguments }
```

## 解决的核心问题：N×M → N+M

- **之前**: 每个 LLM 提供商需要为每个工具编写独立集成代码（OpenAI function format, Anthropic tool format, Gemini function format → N×M）
- **之后**: 一次编写 MCP Server，所有兼容客户端可用（N+M）

## 2026 生态

- 官方 Server: GitHub、Slack、PostgreSQL、Filesystem、Web Search
- 社区注册: 13000+ 开源 MCP Server
- IDE 集成: VS Code Copilot、Cursor、JetBrains AI
- 云平台: AWS Bedrock、Azure AI、GCP Vertex 提供托管 MCP 端点

## 生产最佳实践

1. **无状态优先**: 每个请求携带所有必要上下文
2. **认证授权**: 环境变量存密钥；按角色控制工具访问
3. **结构化错误**: 返回机器可读错误（含重试信息），而非纯文本
4. **分页**: 大数据集响应需分页，因为 LLM 上下文窗口有限
5. **不要过度暴露工具**: 过多工具会降低推理质量

## MCP vs 其他方案

| 特性 | MCP | OpenAPI | LangChain Tools |
|------|-----|---------|-----------------|
| 标准化规范 | ✅ | ✅ | ❌ |
| 双向通信 | ✅ | ❌ | ❌ |
| 上下文/资源 | ✅ | ❌ | ❌ |
| 多提供商支持 | ✅ | 部分 | ❌ |
| 实时订阅 | ✅ | ❌ | ❌ |
| 生态成熟度 | 快速增长 | 成熟 | 成熟 |

## 常见陷阱

1. 过度暴露工具 → 降低 LLM 推理质量
2. 缺少工具描述 → 影响 LLM 决策质量
3. 同步阻塞 → MCP handler 应为异步
4. 无分页 → 大响应超出 LLM 上下文
