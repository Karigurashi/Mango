---
title: Agent Configuration
category: Agent配置
related: [Agent Memory, Human-in-the-Loop, Skill System, Tool Use Pattern, Channel Abstraction]
confidence: high
last_compiled: 2026-05-31
---

# Agent Configuration

> Agent 配置即代码模式，通过 AGENTS.md 定义行为约束和操作规则，SOUL.md 定义人格、语气和价值观，实现 Agent 行为的可配置、可版本控制。

# Agent Configuration

> Agent 配置即代码模式，通过 AGENTS.md 定义行为约束和操作规则，SOUL.md 定义人格、语气和价值观，实现 Agent 行为的可配置、可版本控制。

## 概述

**Agent Configuration** 是一种将 Agent 行为参数化的设计模式，采用配置文件（通常为 Markdown 格式）来定义 Agent 的行为、个性、工具访问权限和约束条件。在 Claude Agent SDK 中，配置通过 `max_turns`、`ALLOWED_DIRECTORIES` 等参数控制 Agent 的行为边界。

## 核心要素

- **行为约束**：通过 `AGENTS.md` 定义操作规则和限制
- **人格定义**：通过 `SOUL.md` 定义语气、价值观和交互风格
- **工具权限**：配置 Agent 可访问的工具集（如文件系统、Shell 执行）
- **安全边界**：如 `ALLOWED_DIRECTORIES` 限制文件访问范围，禁止访问凭证文件
- **成本控制**：设置 `max_turns` 防止无限循环，选择模型层级（Haiku/Sonnet）平衡成本

## 相关模式

- [[Agent Memory]]：配置持久化存储策略
- [[Human-in-the-Loop]]：配置人工干预节点
- [[Skill System]]：配置可插拔技能模块
- [[Tool Use Pattern]]：配置工具调用权限
- [[Channel Abstraction]]：配置多通道接入

## 关键事实

- Agent Configuration 通过配置文件定义行为约束和操作规则
- Claude Agent SDK 通过 max_turns、ALLOWED_DIRECTORIES 等参数控制行为边界
- 安全配置包括限制文件访问范围和禁止访问凭证文件
- 成本控制通过设置 max_turns 和选择模型层级实现
