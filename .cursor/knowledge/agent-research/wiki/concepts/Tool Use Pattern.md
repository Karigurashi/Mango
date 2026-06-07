---
title: Tool Use Pattern
category: Agent架构
related: [Single Agent + Tools, Single Agent + MCP Servers + Tools, ReAct Pattern, Skill System]
confidence: high
last_compiled: 2026-05-31
---

# Tool Use Pattern

> Agent 通过工具调用与外部世界交互，工具封装了文件系统、Shell 执行、API 调用等能力，是 Agent 能力扩展的核心机制。

# Tool Use Pattern

> Agent 通过工具调用与外部世界交互，工具封装了文件系统、Shell 执行、API 调用等能力，是 Agent 能力扩展的核心机制。

## 概述

**Tool Use Pattern**（工具使用模式）是 Agent 与外部世界交互的核心机制。在 Claude Agent SDK 中，工具分为内置工具（read、write、edit、glob、grep、bash、task）和自定义工具（通过 @tool 装饰器定义）。

## 工具类型

- **内置工具**：SDK 提供的标准工具
- **自定义工具**：开发者通过 @tool 装饰器定义
- **MCP 工具**：通过 MCP 服务器提供的工具

## 工具定义

自定义工具通过函数签名 + 描述定义，Agent 自动决定何时调用。

## 相关模式

- [[Single Agent + Tools]]：单 Agent 工具
- [[Single Agent + MCP Servers + Tools]]：MCP 工具
- [[ReAct Pattern]]：思考-行动循环
- [[Skill System]]：技能系统

## 关键事实

- Tool Use Pattern 是 Agent 与外部世界交互的核心机制
- Claude Agent SDK 提供内置工具和自定义工具支持
- 通过 @tool 装饰器定义自定义工具
- 工具封装了文件系统、Shell 执行、API 调用等能力
