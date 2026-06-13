---
title: Graph-based Agents
category: Agent架构
related: [Hierarchical Agents, Swarm Agents, Human-in-the-Loop, Agent Memory, Multi-Agent Collaboration, Hybrid Architectures, Single Agent + Tools, Sequential Agents, Parallel Agents]
confidence: high
last_compiled: 2026-05-31
---

# Graph-based Agents

> 基于有向图的工作流引擎（如 LangGraph），通过 State、Nodes、Edges 显式定义 Agent 流程，支持 Supervisor、Handoff、Hierarchical、Custom Workflow 等多种多 Agent 模式。

# Graph-based Agents

> 基于有向图的工作流引擎（如 LangGraph），通过 State、Nodes、Edges 显式定义 Agent 流程，支持 Supervisor、Handoff、Hierarchical、Custom Workflow 等多种多 Agent 模式。

## 概述

**Graph-based Agents** 将 Agent 工作流建模为有向图，其中节点（Nodes）代表处理步骤，边（Edges）代表控制流和数据流。状态（State）在节点间传递，实现复杂的多 Agent 协作。

## 核心概念

- **State**：全局状态，在节点间传递
- **Nodes**：处理步骤（Agent 调用、工具执行等）
- **Edges**：控制流和数据流
- **Supervisor**：监督者节点协调子 Agent
- **Handoff**：Agent 间任务交接

## 相关模式

- [[Hierarchical Agents]]：层级结构
- [[Swarm Agents]]：群体协作
- [[Human-in-the-Loop]]：人工干预节点
- [[Agent Memory]]：状态持久化
- [[Multi-Agent Collaboration]]：多 Agent 协作
- [[Hybrid Architectures]]：混合架构
- [[Single Agent + Tools]]：单 Agent 工具调用
- [[Sequential Agents]]：顺序执行
- [[Parallel Agents]]：并行执行

## 关键事实

- Graph-based Agents 通过 State、Nodes、Edges 定义工作流
- 支持 Supervisor、Handoff、Hierarchical 等多种模式
- LangGraph 是典型实现框架
- 状态在节点间传递实现复杂协作
