---
title: Single Agent + Tools
category: Agent架构
related: [Tool Use Pattern, ReAct Pattern, Single Agent + MCP Servers + Tools, Agent Memory]
confidence: high
last_compiled: 2026-05-31
---

# Single Agent + Tools

> 单个 Agent 直接调用内置或自定义工具（如文件读写、Shell 执行、代码搜索），通过 ReAct 循环完成复杂任务。

# Single Agent + Tools

> 单个 Agent 直接调用内置或自定义工具（如文件读写、Shell 执行、代码搜索），通过 ReAct 循环完成复杂任务。

## 概述

**Single Agent + Tools** 是最基础的 Agent 模式，单个 Agent 通过工具调用扩展能力。在 Claude Agent SDK 中，内置工具包括 `read`、`write`、`edit`、`glob`、`grep`、`bash`、`task`（子代理启动），同时支持通过 `@tool` 装饰器定义自定义工具。

## 内置工具

- **read**：读取文件内容
- **write**：写入文件
- **edit**：编辑文件
- **glob**：文件模式匹配
- **grep**：文本搜索
- **bash**：Shell 命令执行
- **task**：启动子代理

## 自定义工具

通过 `@tool` 装饰器定义函数签名 + 描述，Agent 自动决定何时调用。

## 相关模式

- [[Tool Use Pattern]]：工具调用模式
- [[ReAct Pattern]]：思考-行动循环
- [[Single Agent + MCP Servers + Tools]]：MCP 工具集成
- [[Agent Memory]]：记忆系统

## 关键事实

- Single Agent + Tools 是最基础的 Agent 模式
- Claude Agent SDK 内置 read、write、edit、glob、grep、bash、task 等工具
- 通过 @tool 装饰器支持自定义工具
- Agent 通过 ReAct 循环决定何时调用工具
