# LangGraph 多 Agent 系统（2026）

来源: LifeTidesHub "LangGraph Multi-Agent Systems Complete Guide 2026", LangChain 官方博客

## 概述

LangGraph 是 LangChain 的低级编排框架，无隐藏提示词、无强制"认知架构"。2026 年已成为多 Agent 生产标准。

## 核心概念

### State（状态）
共享的、可持久化的状态对象，在 Agent 间传递。基于 TypedDict 定义，支持 Pydantic 验证。

### Nodes（节点）
图中的处理单元，可以是 Agent、工具调用、API 调用、条件判断。

### Edges（边）
定义信息流方向：普通边（固定流向）、条件边（基于状态动态路由）。

### Graph（图）
由节点和边组成的有向图，编译后成为可执行工作流。

## 多 Agent 架构模式

### 1. Supervisor（监督者模式）
一个中央"监督者" Agent 接收任务，决定调用哪个 Worker Agent，汇总结果。

适用: 任务类型明确可分派，需要中央协调。

### 2. Handoff / Swarm（交接/群体模式）
Agent 之间直接交接任务，无需中央协调器。每个 Agent 决定下一步交给谁。

适用: 客服系统（不同 Agent 处理不同问题类别）。

### 3. Hierarchical（层级模式）
树形结构：顶级 Agent 分解 → 中级 Agent 协调 → 底层 Agent 执行。

适用: 复杂企业工作流。

### 4. Custom Workflow Graph（自定义工作流图）
完全自定义的图结构，适合非标准流程。

## 关键设计选择

- **State 设计**: 决定哪些信息在 Agent 间共享，直接影响架构复杂度
- **Human-in-the-Loop**: LangGraph 原生支持 `interrupt` 在任意节点暂停等待人类输入
- **Memory**: 短期记忆通过 State 实现，长期记忆需外接持久化存储
- **Streaming**: 支持节点级和 Token 级流式输出

## 与其他框架对比

| | LangGraph | CrewAI | AutoGen |
|---|---|---|---|
| 控制粒度 | 最低级（节点/边） | 高级（角色定义） | 中级（Agent 对话） |
| 灵活性 | 最高 | 中 | 中 |
| 学习曲线 | 陡峭 | 平缓 | 中等 |

LangGraph 适合需要精确控制工作流的场景；CrewAI 适合快速原型；AutoGen 适合对话式多 Agent 交互。
