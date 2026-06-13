---
title: Tree of Thoughts Pattern
category: Agent架构
related: [ReAct Pattern, Plan and Solve Pattern, Reflection Pattern, Dynamic Planning Pattern]
confidence: medium
last_compiled: 2026-05-31
---

# Tree of Thoughts Pattern

> 探索多条推理路径的树状结构，Agent 在决策点分叉出多个思考分支，通过评估和回溯选择最优路径。

# Tree of Thoughts Pattern

> 探索多条推理路径的树状结构，Agent 在决策点分叉出多个思考分支，通过评估和回溯选择最优路径。

## 概述

**Tree of Thoughts Pattern**（思维树模式）让 Agent 在推理过程中探索多条路径，在决策点分叉出多个思考分支，通过评估各分支的结果选择最优路径。

## 核心机制

- **分支探索**：在决策点生成多个思考分支
- **路径评估**：评估各分支的可行性
- **回溯剪枝**：放弃低质量分支
- **最优选择**：选择最优推理路径

## 相关模式

- [[ReAct Pattern]]：单路径思考
- [[Plan and Solve Pattern]]：计划与执行
- [[Reflection Pattern]]：反思优化
- [[Dynamic Planning Pattern]]：动态调整

## 关键事实

- Tree of Thoughts Pattern 探索多条推理路径
- 在决策点分叉出多个思考分支
- 通过评估和回溯选择最优路径
- 适用于需要探索多种可能性的复杂推理任务
