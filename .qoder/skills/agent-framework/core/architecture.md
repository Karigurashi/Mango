# 核心架构

Brain Agent 借鉴 Unity 的 GameObject + Component 思想，将 Agent 拆解为 Entity 容器与 Component 能力单元。

## Entity-Component 模式

- **BaseAgent**：Entity 容器，本身不含业务逻辑，只持有 `Dict[Type[IComponent], IComponent]`，暴露 AddComponent / GetComponent / RemoveComponent / Destroy。
- **IComponent**：每一项独立能力封装为一个 Component。构造时仅做字段默认值，业务依赖统一在 `OnInitialize` 阶段注入。

| 维度 | 收益 |
|------|------|
| 解耦 | Component 通过 `agent.GetComponent(T)` 引用，不在构造函数互传 |
| 生命周期统一 | AddComponent → GetComponent（惰性触发OnInitialize）→ OnDestroy 三阶段固定 |
| 扩展性 | 新增能力只需实现 IComponent 并 AddComponent |
| 可测试 | 可单独构造 Component 注入 Mock Agent |

## BaseAgent 容器

核心约束：

- **类型即键**：`_components` 是 `Dict[Type, IComponent]`，同类型组件唯一，O(1) 查找。
- **构造无参**：AddComponent 内部 `T()`，业务参数禁止入参。
- **惰性初始化**：AddComponent 仅构造；GetComponent 首次访问时自动触发 OnInitialize，通过 `_initializedComponents` 保证幂等。
- **RemoveComponent / Destroy**：调用 OnDestroy 释放外部资源。

## IComponent 生命周期

```
未挂载 → [AddComponent] → 已挂载待初始化 → [GetComponent首次] → 运行中 → [Remove/Destroy] → OnDestroy已回调
```

| 阶段 | 调用方 | 约束 |
|------|--------|------|
| `__init__()` | AddComponent 内部 | 仅字段默认值，不可访问其他 Component |
| `OnInitialize(agent)` | GetComponent 首次访问 | 通过 `agent.GetComponent()` 注入依赖 |
| `OnDestroy()` | RemoveComponent / Destroy | 释放外部资源 |

**组件间通信唯一规范**：必须通过 `agent.GetComponent(TargetComponent)` 获取，禁止作为参数互传。

## 组件注册顺序与依赖

Agent 构造时通过 AddComponent + GetComponent 序列挂载：

```
1. AddComponent(DataComponent)        ← 仅构造，预注入 llm + config
2. GetComponent(EventBusComponent)    ← 惰性初始化
3. GetComponent(LLMComponent)         ← 依赖 Data.llm + EventBus
4. GetComponent(SessionComponent)     ← 依赖 Memory（可选） + LLM
5. GetComponent(ContextComponent)     ← 依赖 Session + LLM + Data + EventBus
6. GetComponent(RuleComponent)
7. GetComponent(SkillComponent)
8. GetComponent(McpComponent)
9. GetComponent(ToolComponent)
10. GetComponent(HarnessComponent)    ← 依赖以上全部
```

依赖关系：

```
HarnessComponent  → Context / Rule / Skill / Mcp / Tool / Data
ContextComponent  → Session / LLM / Data / EventBus
LLMComponent      → Data + EventBus
SessionComponent  → Memory(optional) + LLM
```

首次 RunStreamAsync/RunAsync 时 HarnessComponent.BuildAsync() 完成 LOD0 装填和工具绑定。

## 双模调用

Agent 暴露两种入口，事件统一通过 EventBusComponent 推送：

| 方法 | 流式 | 说明 |
|------|------|------|
| RunStreamAsync | 是 | 逐 token 增量推送 |
| RunAsync | 否 | 单次完整响应 |

- 入参均为 `(userMessage, cancellationToken)`，出参均为 None。
- `_runLock`（asyncio.Lock）防止同 Agent 并发重入。
- finally 中执行 ContextComponent.AfterTurnAsync() 确保清理。

## EAgentState 状态机

```
IDLE → THINKING ↔ ACTING
         ↓          ↓
      FINISHED ←───┘
         ↓
       ERROR
```

- DataComponent.state setter 校验转移合法性，**非法仅警告不阻断**。
- 状态变更通过 EventBusComponent 推送 StateChange 事件。

## SimpleAgent

仅挂载 DataComponent + LLMComponent + EventBusComponent 的纯对话 Agent。无 ReAct、无工具、无 Context、无 Harness。RunStreamAsync 直接调用 LLMComponent.StreamAsync 返回单轮文本。适合纯对话场景或作为新 Agent 的脚手架参考。
