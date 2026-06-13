# AI Agent 八大架构模式（2025）

来源: DEV Community "The Ultimate Guide to AI Agent Architectures in 2025"

## 1. Single Agent + Tools（单 Agent + 工具）

**核心**: 一个语言模型充当"大脑"，决定何时使用哪些工具。

组件: LLM + 工具定义 + 记忆系统 + 控制流逻辑 + 执行环境。

**控制流**: ReAct 模式（Reasoning + Acting）→ 思考→行动→观察→循环。

**优势**: 简单任务成本低（比复杂架构低 50%）；HumanEval 基准上简单设计加策略重试可匹配甚至超过复杂架构。

**限制**: 
- 上下文窗口约束（所有推理、工具、记忆在一个窗口）
- 工具过载（超过 8-10 个工具性能下降）
- 错误传播（早期推理错误级联放大）
- 复杂多步规划表现下降

## 2. Sequential Agents（顺序 Agent）

**核心**: 多个专用 Agent 按预定顺序执行，每个 Agent 处理前一 Agent 的输出。

**控制流**: 初始 Agent → Agent 2 → Agent 3 → ... → 最终 Agent → 响应。可选反馈回路回到前序阶段。

**性能**: 复杂任务完成率高 15-25%，领域子任务准确率高 30-40%，更强韧性，更经济（昂贵模型仅用于必要步骤）。

**限制**: 信息在 Agent 间传递丢失、错误向下游放大、编排复杂度、顺序处理延迟、缺乏适应性。

## 3. Single Agent + MCP Servers + Tools

**核心**: 基于 MCP（Model Context Protocol）客户端-服务器模型，标准化 AI 模型与外部数据和工具的交互。

**解决 N×M 问题**: 传统方案每个 LLM 提供商需要独立集成每个工具（N×M）；MCP 将其变为 N+M（一次编写，所有客户端可用）。

## 4. Hierarchical Agents（层级 Agent）

**核心**: 树形结构，顶层监督者分解任务，中间层管理者协调，底层工作者执行。

## 5. Parallel Agents（并行 Agent）

**核心**: 多个 Agent 同时处理同一任务的不同方面，结果由汇总 Agent 合并。

## 6. Swarm Agents（群体 Agent）

**核心**: 去中心化，Agent 自主决定与其他 Agent 交互，无中央编排器。

## 7. Graph-based Agents（图 Agent）

**核心**: 用有向图定义 Agent 工作流（LangGraph 为代表），节点=Agent/工具/决策点，边=信息流。

## 8. Hybrid Architectures（混合架构）

**核心**: 根据任务需求组合多种模式，例如层级编排 + 并行执行 + 人在回路。
