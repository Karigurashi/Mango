---
title: Plan and Solve Pattern
category: Agent架构
related: [Dynamic Planning Pattern, ReAct Pattern, Task-Decoupled Planning Pattern, Reflection Pattern]
confidence: high
last_compiled: 2026-05-31
---

# Plan and Solve Pattern

> 先制定完整计划再逐步执行，将复杂问题分解为可管理的子步骤，提高任务完成的准确性和可追溯性。

# Plan and Solve Pattern

> 先制定完整计划再逐步执行，将复杂问题分解为可管理的子步骤，提高任务完成的准确性和可追溯性。

## 概述

**Plan and Solve Pattern**（计划与解决模式）是 Agent 先制定完整执行计划，然后按计划逐步执行的策略。在 Claude Agent SDK 中，Agent 循环遵循 "规划→执行→观察→重复" 的模式。

## 核心流程

1. **任务分析**：理解用户需求
2. **计划制定**：生成详细的执行步骤
3. **逐步执行**：按计划顺序执行
4. **结果验证**：检查执行结果

## 相关模式

- [[Dynamic Planning Pattern]]：动态调整计划
- [[ReAct Pattern]]：思考-行动-观察
- [[Task-Decoupled Planning Pattern]]：计划与执行分离
- [[Reflection Pattern]]：反思优化

## 关键事实

- Plan and Solve Pattern 先制定完整计划再逐步执行
- 将复杂问题分解为可管理的子步骤
- Claude Agent SDK 遵循规划→执行→观察→重复的循环
- 提高任务完成的准确性和可追溯性
