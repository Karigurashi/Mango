---
title: Dynamic Planning Pattern
category: Agent架构
related: [Plan and Solve Pattern, ReAct Pattern, Task-Decoupled Planning Pattern, Hybrid Architectures]
confidence: medium
last_compiled: 2026-05-31
---

# Dynamic Planning Pattern

> 在执行过程中根据中间结果动态调整后续计划，克服静态计划的僵化，提高对不确定环境的适应性。

# Dynamic Planning Pattern

> 在执行过程中根据中间结果动态调整后续计划，克服静态计划的僵化，提高对不确定环境的适应性。

## 概述

**Dynamic Planning** 允许 Agent 不等到整个计划执行完毕才调整，而是在接收到每一步的反馈后，实时决定后续步骤，必要时重新规划剩余部分。它是 [[Plan and Solve Pattern]] 的增强变体（Plan-and-Act），也常见于 ReAct 模式中。

## 核心流程

1. **任务输入**：接收用户任务
2. **初始规划**：生成初步执行计划
3. **执行与观察**：执行一步，观察结果
4. **动态调整**：根据中间结果调整后续计划
5. **重复**：直到任务完成

## 相关模式

- [[Plan and Solve Pattern]]：静态计划基础
- [[ReAct Pattern]]：思考-行动-观察循环
- [[Task-Decoupled Planning Pattern]]：计划与执行分离
- [[Hybrid Architectures]]：组合多种规划策略

## 关键事实

- Dynamic Planning 根据中间结果动态调整后续计划
- 克服静态计划的僵化，提高对不确定环境的适应性
- 是 Plan-and-Act 模式的典型实现
- 常见于 ReAct 模式中
