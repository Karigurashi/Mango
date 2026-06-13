---
title: MCP Protocol
category: Agent协议
related: [Single Agent + MCP Servers + Tools, Tool Use Pattern, Skill System, Agent Configuration]
confidence: high
last_compiled: 2026-05-31
---

# MCP Protocol

> Model Context Protocol（MCP）是 Anthropic 提出的开放协议，标准化 LLM 应用与外部数据源和工具之间的交互方式，支持动态工具发现、类型安全和双向通信。

# MCP Protocol

> Model Context Protocol（MCP）是 Anthropic 提出的开放协议，标准化 LLM 应用与外部数据源和工具之间的交互方式，支持动态工具发现、类型安全和双向通信。

## 概述

**MCP Protocol**（Model Context Protocol）是 Anthropic 提出的开放协议，旨在标准化 LLM 应用与外部数据源和工具之间的交互方式。在 Claude Agent SDK 中，MCP 服务器集成是原生支持的，可扩展数据库、API、第三方服务。

## 核心特性

- **动态工具发现**：MCP 服务器可动态注册和发现工具
- **类型安全**：工具输入输出有明确的类型定义
- **双向通信**：支持请求-响应和事件推送
- **标准化接口**：统一的工具调用协议

## 相关模式

- [[Single Agent + MCP Servers + Tools]]：MCP 工具集成
- [[Tool Use Pattern]]：工具调用模式
- [[Skill System]]：技能系统
- [[Agent Configuration]]：MCP 服务器配置

## 关键事实

- MCP Protocol 是 Anthropic 提出的开放协议
- 标准化 LLM 应用与外部数据源和工具的交互
- Claude Agent SDK 原生支持 MCP 服务器集成
- 支持动态工具发现、类型安全和双向通信
