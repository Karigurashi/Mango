---
title: Parallel Agents
category: Agent架构
related: [Sequential Agents, Swarm Agents, Hierarchical Agents, Graph-based Agents, Multi-Agent Collaboration]
confidence: high
last_compiled: 2026-05-31
---

# Parallel Agents

> 多个 Agent 同时独立执行子任务，通过任务分解和结果聚合加速处理，适用于可并行化的独立子任务。

# Parallel Agents

> 多个 Agent 同时独立执行子任务，通过任务分解和结果聚合加速处理，适用于可并行化的独立子任务。

## 概述

**Parallel Agents**（并行 Agent）模式将任务分解为多个独立子任务，由多个 Agent 同时执行，最后聚合结果。在 Claude Agent SDK 中，通过 `task` 工具可启动独立 Claude 实例并行工作，每个子代理在隔离上下文中运行，独立返回结果。

## 核心机制

- **任务分解**：将主任务拆分为独立子任务
- **并行执行**：多个 Agent 同时工作
- **上下文隔离**：每个子代理在独立上下文中运行
- **结果聚合**：收集并合并所有子代理结果

## 适用场景

- 大规模代码审查
- 多文件并行处理
- 独立数据查询
- 批量文档生成

## 相关模式

- [[Sequential Agents]]：顺序执行
- [[Swarm Agents]]：群体协作
- [[Hierarchical Agents]]：层级管理
- [[Graph-based Agents]]：图工作流
- [[Multi-Agent Collaboration]]：多 Agent 协作

## 关键事实

- Parallel Agents 通过多个 Agent 同时执行独立子任务
- Claude Agent SDK 通过 task 工具启动并行子代理
- 每个子代理在隔离上下文中运行
- 适用于可并行化的独立子任务
