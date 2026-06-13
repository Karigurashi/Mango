---
title: Human-in-the-Loop
category: Agent架构
related: [Graph-based Agents, Hierarchical Agents, Reflection Pattern, Multi-Agent Collaboration, Hybrid Architectures]
confidence: high
last_compiled: 2026-05-31
---

# Human-in-the-Loop

> Agent 在关键节点（如审批门）暂停执行，通知人类操作员提供建议动作、推理和上下文，等待审批/纠正后恢复；LangGraph 原生支持 interrupt 实现在任意节点插入人工干预。

# Human-in-the-Loop

> Agent 在关键节点（如审批门）暂停执行，通知人类操作员提供建议动作、推理和上下文，等待审批/纠正后恢复；LangGraph 原生支持 interrupt 实现在任意节点插入人工干预。

## 概述

**Human-in-the-Loop（人机协同）模式** 在 Agent 工作流中引入人工干预节点，确保关键决策得到人类确认。

## 核心机制

- **中断点**：Agent 在关键节点暂停执行
- **通知**：向人类操作员提供建议动作、推理和上下文
- **等待**：等待人类审批或纠正
- **恢复**：根据人类反馈继续执行

## 相关模式

- [[Graph-based Agents]]：图工作流中的中断点
- [[Hierarchical Agents]]：层级结构中的审批门
- [[Reflection Pattern]]：反思结果需要人类确认
- [[Multi-Agent Collaboration]]：多 Agent 协作中的人类监督
- [[Hybrid Architectures]]：混合架构中嵌入人工干预

## 关键事实

- Human-in-the-Loop 在关键节点引入人工干预
- Agent 暂停执行并通知人类操作员
- LangGraph 原生支持 interrupt 实现
- 确保关键决策得到人类确认
