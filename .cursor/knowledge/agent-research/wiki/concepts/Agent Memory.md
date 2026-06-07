---
title: Agent Memory
category: Agent基础设施
related: [Single Agent + Tools, Reflection Pattern, Plan and Solve Pattern, Dynamic Planning Pattern, Hub-and-Spoke Agents, Channel Abstraction]
confidence: high
last_compiled: 2026-05-31
---

# Agent Memory

> 持久化存储对话历史、实体记忆和知识图谱，结合状态持久化与可观测性，为 Agent 提供长期上下文和决策追溯能力。

# Agent Memory

> 持久化存储对话历史、实体记忆和知识图谱，结合状态持久化与可观测性，为 Agent 提供长期上下文和决策追溯能力。

## 概述
**Agent Memory**（记忆系统）是 Agent 持续运行的基础，它不仅存储短期的对话上下文，还包括长期实体记忆（用户偏好、事实知识）和结构化知识图谱。在 Claude Agent SDK 中，上下文管理是自动化的——SDK 自动处理上下文压缩与摘要，支持长生命周期 Agent（超过 100 轮）通过子代理并行处理来管理上下文。

## 核心能力

- **短期上下文**：当前对话轮次的交互历史
- **长期记忆**：用户偏好、事实知识等持久化存储
- **知识图谱**：实体间关系的结构化表示
- **自动压缩**：SDK 自动对长上下文进行压缩与摘要
- **子代理隔离**：子代理在独立上下文中运行，避免上下文污染

## 相关模式

- [[Single Agent + Tools]]：工具调用结果存入记忆
- [[Reflection Pattern]]：反思结果更新记忆
- [[Plan and Solve Pattern]]：计划状态持久化
- [[Dynamic Planning Pattern]]：动态调整依赖记忆
- [[Hub-and-Spoke Agents]]：中心化记忆共享
- [[Channel Abstraction]]：跨通道记忆一致性

## 关键事实

- Agent Memory 持久化存储对话历史、实体记忆和知识图谱
- Claude Agent SDK 自动处理上下文压缩与摘要
- 长生命周期 Agent（超过 100 轮）通过子代理并行管理上下文
- 子代理在独立上下文中运行，避免上下文污染
