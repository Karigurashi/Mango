---
title: Reflection Pattern
category: Agent架构
related: [ReAct Pattern, Plan and Solve Pattern, Human-in-the-Loop, Agent Memory]
confidence: high
last_compiled: 2026-05-31
---

# Reflection Pattern

> Agent 对自身输出进行自我检查和修正，通过多轮反思提高回答质量和准确性。

# Reflection Pattern

> Agent 对自身输出进行自我检查和修正，通过多轮反思提高回答质量和准确性。

## 概述

**Reflection Pattern**（反思模式）让 Agent 对自己的输出进行自我评估和修正，通过多轮反思循环提高质量。

## 核心流程

1. **初始输出**：Agent 生成初步回答
2. **自我检查**：Agent 评估自己的输出质量
3. **修正**：根据评估结果改进输出
4. **重复**：直到满足质量标准

## 相关模式

- [[ReAct Pattern]]：思考-行动循环
- [[Plan and Solve Pattern]]：计划与执行
- [[Human-in-the-Loop]]：人工评估
- [[Agent Memory]]：反思结果存储

## 关键事实

- Reflection Pattern 让 Agent 对自身输出进行自我检查和修正
- 通过多轮反思循环提高回答质量
- Agent 评估自己的输出质量并改进
- 可结合 Human-in-the-Loop 进行人工评估
