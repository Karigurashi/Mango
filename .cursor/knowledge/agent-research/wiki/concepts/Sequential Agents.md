---
title: Sequential Agents
category: Agent架构
related: [Parallel Agents, Graph-based Agents, Multi-Agent Collaboration, Hierarchical Agents]
confidence: high
last_compiled: 2026-05-31
---

# Sequential Agents

> 多个 Agent 按顺序流水线执行，前一个 Agent 的输出作为后一个 Agent 的输入，适用于有明确依赖关系的任务链。

# Sequential Agents

> 多个 Agent 按顺序流水线执行，前一个 Agent 的输出作为后一个 Agent 的输入，适用于有明确依赖关系的任务链。

## 概述

**Sequential Agents**（顺序 Agent）模式将任务分解为有依赖关系的步骤链，每个 Agent 处理一个步骤，前一个 Agent 的输出传递给后一个 Agent。

## 核心机制

- **流水线处理**：Agent 按顺序执行
- **依赖传递**：前一个输出作为后一个输入
- **状态累积**：中间结果逐步累积

## 适用场景

- 数据处理管道
- 多阶段内容生成
- 审批流程

## 相关模式

- [[Parallel Agents]]：并行执行
- [[Graph-based Agents]]：图工作流
- [[Multi-Agent Collaboration]]：多 Agent 协作
- [[Hierarchical Agents]]：层级管理

## 关键事实

- Sequential Agents 按顺序流水线执行
- 前一个 Agent 的输出作为后一个 Agent 的输入
- 适用于有明确依赖关系的任务链
- 中间结果逐步累积
