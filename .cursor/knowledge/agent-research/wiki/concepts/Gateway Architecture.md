---
title: Gateway Architecture
category: Agent架构
related: [Channel Abstraction, Skill System, Single Agent + Tools, Multi-Agent Collaboration, Graph-based Agents, Hybrid Architectures]
confidence: high
last_compiled: 2026-05-31
---

# Gateway Architecture

> Gateway（网关）作为控制平面，负责接收多通道输入、路由到对应 Agent/Skill、聚合结果并返回，实现 Hub-and-Spoke 架构。

# Gateway Architecture

> Gateway（网关）作为控制平面，负责接收多通道输入、路由到对应 Agent/Skill、聚合结果并返回，实现 Hub-and-Spoke 架构。

## 概述

**Gateway Architecture** 是一种 Hub-and-Spoke 架构模式，常用于个人 AI 助手或企业级多 Agent 系统。Gateway 作为统一入口，将通道协议与 Agent 逻辑解耦。

## 核心组件

- **Gateway**：控制平面，负责路由和聚合
- **Channel**：输入/输出通道抽象
- **Agent/Skill**：业务逻辑处理单元

## 相关模式

- [[Channel Abstraction]]：通道抽象支持
- [[Skill System]]：技能路由
- [[Single Agent + Tools]]：单 Agent 工具调用
- [[Multi-Agent Collaboration]]：多 Agent 协作
- [[Graph-based Agents]]：图工作流集成
- [[Hybrid Architectures]]：混合架构组合

## 关键事实

- Gateway 作为控制平面负责路由和聚合
- 实现通道协议与 Agent 逻辑的解耦
- 常用于个人 AI 助手或企业级多 Agent 系统
- 支持多通道统一入口
