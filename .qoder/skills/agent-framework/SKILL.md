---
name: agent-framework
description: Brain Agent 框架核心，采用 Unity 风格 Entity-Component 架构，提供 ReAct 循环编排、双模 LLM 调用（流式/非流式）、LOD 四级上下文管理、工具系统、事件推送、技能渐进式披露。修改 agent/ 目录下任何组件、扩展新 Component、排查 Agent 运行时问题时参考。
---

# Agent 框架

## 架构总览

```
AgentConfig + BaseLLM
       │
       ▼
 Agent(BaseAgent)  ──持有──▶  Components 字典
       │                        ├─ DataComponent        配置 + 状态机 + LLM 句柄
       │                        ├─ LLMComponent         四维 LLM 调用 + 工具绑定 + 事件推送
       │                        ├─ SessionComponent     多会话消息账本
       │                        ├─ ContextComponent     LOD 调度器 + 增量估算
       │                        ├─ ToolComponent        工具注册 + 调度
       │                        ├─ HarnessComponent     LOD0 装填线束
       │                        ├─ RuleComponent       规则触发
       │                        ├─ SkillComponent       Skill 渐进式披露
       │                        ├─ McpComponent         MCP Server
       │                        ├─ MemoryComponent      跨会话记忆
       │                        └─ EventBusComponent    流事件推送
       ▼
 ReAct Loop  ──Think──▶  LLMComponent.StreamAsync
       ▲                    │
       │                    ▼
       └──Observe── ToolComponent.DispatchBatchAsync ──▶ EventBusComponent.Push
```

## 关键概念

| 概念 | 说明 |
|------|------|
| **BaseAgent** | Entity 容器，持有 `Dict[Type[IComponent], IComponent]`，提供 AddComponent / GetComponent / RemoveComponent / Destroy |
| **惰性初始化** | AddComponent 仅构造（不触发 OnInitialize）；GetComponent 首次访问时自动触发 OnInitialize，`_initializedComponents` 保证幂等 |
| **IComponent** | 组件接口，构造禁带业务参数；OnInitialize(agent) 通过 GetComponent 注入依赖；OnDestroy 资源清理 |
| **Agent** | 完整 ReAct 编排器，挂载全部 Component |
| **SimpleAgent** | 仅挂 Data + LLM + EventBus 的纯对话 Agent，无 ReAct、无工具 |
| **双模调用** | RunStreamAsync(流式) / RunAsync(非流式)，事件通过 EventBusComponent 推送 |
| **EAgentState** | IDLE → THINKING → ACTING → FINISHED/ERROR，非法转移仅警告不阻断 |
| **CancellationToken** | 协作式取消，贯穿 LLM 调用、重试退避、工具执行 |
| **AgentStreamEvent** | 统一流事件：TurnStart / ThinkingDelta / TextDelta / ToolStart / ToolResult / StateChange / Compaction / Error / Done |
| **EventBusComponent** | Subscribe 注册监听器，Push 广播事件并自动归还对象池 |

## 文档索引

| 文档 | 内容 |
|------|------|
| [core/architecture.md](core/architecture.md) | Entity-Component 模式、BaseAgent 容器、IComponent 生命周期、组件依赖图、状态机 |
| [core/agent.md](core/agent.md) | Agent 执行流：双模调用、ReAct 循环、事件系统、并发安全、生命周期 |
| [component/data.md](component/data.md) | DataComponent：配置结构与状态机 |
| [component/llm.md](component/llm.md) | LLMComponent：四维 LLM 调用、事件推送内聚 |
| [component/tool.md](component/tool.md) | ToolComponent：BaseTool 模式、注册调度、内置工具清单 |
| [component/contex.md](component/contex.md) | ContextComponent：LOD 四级分级、四阶段生命周期、两优先级压缩 |
| [component/session.md](component/session.md) | SessionComponent：消息账本、多会话、与 Context 分工 |
| [component/harness.md](component/harness.md) | HarnessComponent：BuildAsync 装载流程、LOD0 注入序 |
| [component/extensions.md](component/extensions.md) | Rule 规则引擎、MCP Server 管理、Memory 跨会话记忆 |
