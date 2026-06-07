---
title: ReAct Pattern
category: Agent架构
related: [Plan and Solve Pattern, Dynamic Planning Pattern, Tool Use Pattern, Reflection Pattern]
confidence: high
last_compiled: 2026-05-31
---

# ReAct Pattern

> 思考（Reasoning）→ 行动（Acting）→ 观察（Observation）循环，Agent 在每一步推理后执行工具调用，根据观察结果调整下一步推理。

# ReAct Pattern

> 思考（Reasoning）→ 行动（Acting）→ 观察（Observation）循环，Agent 在每一步推理后执行工具调用，根据观察结果调整下一步推理。

## 概述

**ReAct Pattern**（推理-行动模式）是 Agent 的核心交互模式，Agent 在每一步进行推理，决定调用哪个工具，观察工具返回结果，然后继续推理。在 Claude Agent SDK 中，每次迭代 Claude 决定下一步 → 调用工具 → 接收输出 → 决定继续或结束。

## 核心循环

1. **思考**：分析当前状态，决定下一步行动
2. **行动**：调用工具或执行操作
3. **观察**：接收工具返回结果
4. **重复**：根据观察继续思考

## 相关模式

- [[Plan and Solve Pattern]]：计划与执行
- [[Dynamic Planning Pattern]]：动态调整
- [[Tool Use Pattern]]：工具调用
- [[Reflection Pattern]]：反思优化

## 关键事实

- ReAct Pattern 是思考→行动→观察的循环
- Agent 在每一步推理后执行工具调用
- Claude Agent SDK 每次迭代决定下一步→调用工具→接收输出→决定继续或结束
- 根据观察结果调整下一步推理
