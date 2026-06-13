---
title: Hub-and-Spoke Agents
category: Agent架构
related: [Single Agent + Tools, Channel Abstraction, Multi-Agent Collaboration, Swarm Agents, Hierarchical Agents, Graph-based Agents, Hybrid Architectures]
confidence: high
last_compiled: 2026-05-31
---

# Hub-and-Spoke Agents

> 中心 Gateway 作为控制平面，将用户输入请求路由到对应的 Agent 或 Skill，结果再原路返回，形成星型多 Agent 架构，实现通道与逻辑的解耦。

# Hub-and-Spoke Agents

> 中心 Gateway 作为控制平面，将用户输入请求路由到对应的 Agent 或 Skill，结果再原路返回，形成星型多 Agent 架构，实现通道与逻辑的解耦。

## 概述
**Hub-and-Spoke Agents**（轮辐式架构）是一种中心化多 Agent 架构，Gateway 作为中心枢纽（Hub），各 Agent/Skill 作为辐条（Spoke）。

## 核心组件

- **Hub（Gateway）**：控制平面，负责路由和聚合
- **Spoke（Agent/Skill）**：业务逻辑处理单元
- **Channel**：输入/输出通道

## 相关模式

- [[Single Agent + Tools]]：单 Agent 工具调用
- [[Channel Abstraction]]：通道抽象
- [[Multi-Agent Collaboration]]：多 Agent 协作
- [[Swarm Agents]]：群体协作
- [[Hierarchical Agents]]：层级结构
- [[Graph-based Agents]]：图工作流
- [[Hybrid Architectures]]：混合架构

## 关键事实

- Hub-and-Spoke Agents 采用星型多 Agent 架构
- Gateway 作为中心枢纽负责路由和聚合
- 实现通道协议与 Agent 逻辑的解耦
- 各 Agent/Skill 作为辐条独立运行
