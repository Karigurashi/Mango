---
title: Skill System
category: Agent基础设施
related: [Tool Use Pattern, Agent Configuration, Single Agent + Tools, MCP Protocol]
confidence: high
last_compiled: 2026-05-31
---

# Skill System

> 将 Agent 能力封装为可复用的技能模块，支持动态加载、组合和版本管理，实现能力的模块化扩展。

# Skill System

> 将 Agent 能力封装为可复用的技能模块，支持动态加载、组合和版本管理，实现能力的模块化扩展。

## 概述

**Skill System**（技能系统）将 Agent 的特定能力封装为独立模块，每个技能包含工具定义、提示模板和执行逻辑。

## 核心特性

- **模块化**：每个技能独立封装
- **可复用**：技能可在不同 Agent 间共享
- **动态加载**：按需加载技能
- **版本管理**：技能版本控制

## 相关模式

- [[Tool Use Pattern]]：工具调用
- [[Agent Configuration]]：技能配置
- [[Single Agent + Tools]]：单 Agent 工具
- [[MCP Protocol]]：MCP 技能集成

## 关键事实

- Skill System 将 Agent 能力封装为可复用模块
- 支持动态加载、组合和版本管理
- 每个技能包含工具定义、提示模板和执行逻辑
- 技能可在不同 Agent 间共享
