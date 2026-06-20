---
name: agent-framework
description: Brain Agent 框架核心，采用 Unity 风格 Entity-Component 架构，提供 ReAct 循环编排、四维 LLM 调用（同步/异步×流式/非流式）、LOD 四级上下文管理、工具系统、技能渐进式披露。修改 agent/ 目录下任何组件、扩展新 Component、排查 Agent 运行时问题时参考。
---

# Agent 框架

## 数据流

```
AgentConfig + BaseLLM
       │
       ▼
 Agent(BaseAgent)  ──持有──▶  Components 字典
       │                        ├─ DataComponent       配置 + 状态机 + LLM 句柄
       │                        ├─ LLMComponent        四维 LLM 调用 + 工具绑定
       │                        ├─ SessionComponent    消息账本
       │                        ├─ ContextComponent    LOD 调度器
       │                        ├─ RuleComponent       规则触发
       │                        ├─ SkillComponent      Skill 渐进式披露
       │                        ├─ McpComponent        MCP Server
       │                        ├─ ToolComponent       工具注册 + 调度
       │                        ├─ HarnessComponent    LOD0 装填线束
       │                        └─ LoggingComponent    结构化日志
       ▼
 ReAct Loop  ──Think──▶  LLMComponent.StreamAsync
       ▲                    │
       │                    ▼
       └──Observe── ToolComponent.DispatchAsync ──▶ Stream Events
```

## 快速开始

```python
from llm import LLMManager
from agent import Agent
from agent.component.data.agentConfig import AgentConfig
from agent.agentStreamEvent import EAgentStreamEventType

# 1. 准备 LLM 与配置
llm = LLMManager.GetProvider("deepseek-high")
config = AgentConfig.Default()
config.maxTurns = 10
config.autoCompact = True

# 2. 构造 Agent（自动 AddComponent + InitAllComponents）
agent = Agent(llm, config=config)

# 3. 四维入口任选其一
async for event in agent.RunAsync("帮我读取 README.md"):                # 异步流式
    if event.eventType == EAgentStreamEventType.TEXT_DELTA:
        print(event.content, end="", flush=True)

async for event in agent.RunInvokeAsync("帮我读取 README.md"): ...      # 异步非流式
for event in agent.RunStream("..."): ...                                # 同步流式
for event in agent.RunInvoke("..."): ...                                # 同步非流式

# 4. 取消支持
from common.cancellationToken import CancellationToken
token = CancellationToken()
async for event in agent.RunAsync("...", cancellationToken=token): ...
token.Cancel()  # 中断 LLM 调用与重试退避
```

## 关键概念

| 概念 | 说明 |
|------|------|
| **BaseAgent** | Entity 容器，持有 `Dict[Type[IComponent], IComponent]`，提供 AddComponent / InitAllComponents / GetComponent / Destroy |
| **IComponent** | 组件接口，构造函数禁带业务参数；OnInitialize(agent) 阶段通过 GetComponent 注入依赖；OnDestroy 资源清理 |
| **Agent** | 继承 BaseAgent 的 ReAct 编排器，挂载全部 Component 并实现 `_RunReActCoreAsync` 主循环 |
| **SimpleAgent** | 仅挂 DataComponent + LLMComponent 的纯对话 Agent，无 harness、无 ReAct |
| **四维调用** | RunAsync(异步流) / RunInvokeAsync(异步整) / RunStream(同步流) / RunInvoke(同步整)，同步入口由 RunAsyncGenerator 桥接 |
| **EAgentState** | IDLE → THINKING → ACTING → FINISHED/ERROR/WAITING_USER，非法转移仅警告不阻断 |
| **EContextLodLevel** | RESIDENT(0) / SUMMARIZABLE(1) / DISCARDABLE(2) / EXTERNAL_ONLY(3)，控制压缩与丢弃策略 |
| **CancellationToken** | 协作式取消，贯穿 LLM 调用、重试退避、工具执行 |
| **AgentStreamEvent** | 统一流事件：TextDelta / ToolStart / ToolResultEvent / StateChange / TurnStart / ErrorEvent / Done |

## 文件引用

| 文档 | 内容 |
|------|------|
| [core/architecture.md](core/architecture.md) | Entity-Component 模式、组件依赖图、状态机 |
| [core/flows.md](core/flows.md) | 关键流程时序（初始化、ReAct循环、工具执行、压缩） |
| [core/core.md](core/core.md) | 核心基座层：BaseAgent 容器、IComponent 接口 |
| [core/agent.md](core/agent.md) | Agent 实现层：四维调用、ReAct编排、SimpleAgent |
| [component/data.md](component/data.md) | DataComponent：AgentConfig 配置、状态机 |
| [component/llm.md](component/llm.md) | LLMComponent：LLM 四维调用代理、工具绑定 |
| [component/tool.md](component/tool.md) | ToolComponent + BaseTool：工具注册与调度 |
| [component/contex.md](component/contex.md) | ContextComponent：LOD 四级上下文引擎 |
| [component/session.md](component/session.md) | SessionComponent：消息存储与压缩摘要 |
| [component/harness.md](component/harness.md) | HarnessComponent：线束装载与 LOD0 注入 |
| [component/rule.md](component/rule.md) | RuleComponent：规则四种触发模式 |
| [component/mcp.md](component/mcp.md) | McpComponent：MCP Server 管理 |
| [component/memory.md](component/memory.md) | MemoryComponent：跨会话记忆 |
| [component/logging.md](component/logging.md) | LoggingComponent：结构化日志 |
