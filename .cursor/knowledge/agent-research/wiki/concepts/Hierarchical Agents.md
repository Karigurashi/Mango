---
title: Hierarchical Agents
category: Agent架构
related: [Graph-based Agents, Multi-Agent Collaboration, Swarm Agents, Human-in-the-Loop, Hybrid Architectures]
confidence: high
last_compiled: 2026-05-31
---

# Hierarchical Agents

> 树形层级结构：顶层监督者分解任务并作为中央编排器，中间层管理者协调，底层工作者执行；LangGraph 通过 Supervisor 模式原生支持该架构，并嵌入 Human-in-the-Loop 中断点。

# Hierarchical Agents

> 树形层级结构：顶层监督者分解任务并作为中央编排器，中间层管理者协调，底层工作者执行；LangGraph 通过 Supervisor 模式原生支持该架构，并嵌入 Human-in-the-Loop 中断点。

## 概述

**Hierarchical Agents** 采用树形层级结构组织 Agent，顶层监督者负责任务分解和编排，中间层管理者协调子任务，底层工作者执行具体操作。

## 层级结构

- **顶层监督者**：任务分解、全局编排
- **中间层管理者**：子任务协调、资源分配
- **底层工作者**：具体任务执行

## 相关模式

- [[Graph-based Agents]]：图工作流实现
- [[Multi-Agent Collaboration]]：多 Agent 协作
- [[Swarm Agents]]：群体协作
- [[Human-in-the-Loop]]：人工干预
- [[Hybrid Architectures]]：混合架构

## 关键事实

- Hierarchical Agents 采用树形层级结构
- 顶层监督者负责任务分解和编排
- LangGraph 通过 Supervisor 模式原生支持
- 可嵌入 Human-in-the-Loop 中断点
