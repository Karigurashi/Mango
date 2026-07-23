---
id: agent-llm
title: LLM 组件
aliases:
  - llm
  - 模型
  - chat
  - LLMComponent
roots:
  - agent/component/llm
  - llm
entrypoints:
  - LLMComponent
  - BaseLLM
related:
  - agent-core
summary: "模型调用与消息协议"
---

## 职责

LLM 调用封装与 provider 协议。

## 结构

- Agent 侧：`agent/component/llm`
- Provider：`llm/`
