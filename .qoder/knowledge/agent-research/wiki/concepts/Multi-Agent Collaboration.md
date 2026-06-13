---
title: Multi-Agent Collaboration
category: Agent架构
related: [Hierarchical Agents, Parallel Agents, Swarm Agents, Sequential Agents, Graph-based Agents, Hub-and-Spoke Agents]
confidence: high
last_compiled: 2026-05-31
---

# Multi-Agent Collaboration

> 多个 Agent 通过任务分解、信息共享和结果聚合协同完成复杂任务，支持层级、并行、Swarm 等多种协作模式。

# Multi-Agent Collaboration

> 多个 Agent 通过任务分解、信息共享和结果聚合协同完成复杂任务，支持层级、并行、Swarm 等多种协作模式。

## 概述

**Multi-Agent Collaboration**（多 Agent 协作）是多个 Agent 协同工作的模式集合，通过任务分解、信息共享和结果聚合完成单个 Agent 难以处理的复杂任务。

## 协作模式

- **层级协作**：监督者-工作者模式
- **并行协作**：子代理独立并行工作
- **Swarm 协作**：去中心化群体协作
- **顺序协作**：流水线式处理

## 相关模式

- [[Hierarchical Agents]]：层级协作
- [[Parallel Agents]]：并行协作
- [[Swarm Agents]]：群体协作
- [[Sequential Agents]]：顺序协作
- [[Graph-based Agents]]：图工作流协作
- [[Hub-and-Spoke Agents]]：中心化协作

## 关键事实

- Multi-Agent Collaboration 通过多个 Agent 协同完成复杂任务
- 支持层级、并行、Swarm、顺序等多种协作模式
- 通过任务分解、信息共享和结果聚合实现协作
- Claude Agent SDK 通过 task 工具支持子代理并行工作
