---
title: Single Agent + MCP Servers + Tools
category: Agent架构
related: [MCP Protocol, Single Agent + Tools, Tool Use Pattern, Agent Configuration]
confidence: high
last_compiled: 2026-05-31
---

# Single Agent + MCP Servers + Tools

> 单个 Agent 通过 MCP 协议连接多个工具服务器，实现标准化、可扩展的工具调用能力。

# Single Agent + MCP Servers + Tools

> 单个 Agent 通过 MCP 协议连接多个工具服务器，实现标准化、可扩展的工具调用能力。

## 概述

**Single Agent + MCP Servers + Tools** 模式让单个 Agent 通过 MCP 协议连接多个工具服务器，每个 MCP 服务器提供一组标准化工具。在 Claude Agent SDK 中，MCP 服务器集成是原生支持的，可扩展数据库、API、第三方服务。

## 核心组件

- **Agent**：单一智能体
- **MCP 服务器**：提供标准化工具接口
- **工具**：具体功能实现

## 相关模式

- [[MCP Protocol]]：MCP 协议基础
- [[Single Agent + Tools]]：直接工具调用
- [[Tool Use Pattern]]：工具调用模式
- [[Agent Configuration]]：MCP 服务器配置

## 关键事实

- Single Agent + MCP Servers + Tools 通过 MCP 协议连接多个工具服务器
- Claude Agent SDK 原生支持 MCP 服务器集成
- 可扩展数据库、API、第三方服务
- 实现标准化、可扩展的工具调用
