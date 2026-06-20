# Agent 架构

## 1. Entity-Component 模式

Brain Agent 借鉴 Unity 的 GameObject + Component 思想，将 Agent 拆解为：

- **Entity**：[BaseAgent](file:///c:/Users/Administrator/Desktop/Brain-main/agent/core/baseAgent.py) 作为容器，本身不含业务逻辑，仅持有 Component 字典并暴露挂载/卸载/查询接口。
- **Component**：每一项独立能力（LLM 调用、上下文管理、工具调度、日志……）封装为 [IComponent](file:///c:/Users/Administrator/Desktop/Brain-main/agent/core/baseComponent.py) 子类，构造时仅做字段默认值初始化，业务依赖统一在 OnInitialize 阶段注入。

设计动机：

| 维度 | 收益 |
|------|------|
| 解耦 | Component 之间通过 `agent.GetComponent(T)` 引用，不在构造函数互传，单组件可独立替换 |
| 生命周期统一 | `AddComponent` → `InitAllComponents` → `OnDestroy` 三阶段固定，避免半初始化态 |
| 扩展性 | 新增能力只需实现 IComponent 并 AddComponent，无需修改 Agent 主流程 |
| 可测试 | 可单独构造 Component，注入 Mock Agent，单元测试零耦合 |

## 2. BaseAgent 容器职责

```python
class BaseAgent:
    _components: Dict[Type[IComponent], IComponent]

    AddComponent(compType: Type[T]) -> T            # 无参构造 + 同类型幂等
    InitAllComponents() -> None                      # 按挂载顺序调用 OnInitialize
    GetComponent(compType: Type[T]) -> Optional[T]   # 类型查询
    HasComponent(compType) -> bool
    GetAllComponents() -> List[IComponent]
    RemoveComponent(compType) -> Optional[T]         # 调用 OnDestroy 后弹出
    Destroy() -> None                                # 全量 OnDestroy + 清空
```

关键约束：

- **幂等挂载**：`AddComponent(T)` 若 T 已存在直接返回原实例，不重复构造。
- **类型唯一**：同一类型只能挂载一个实例（值是 dict，key 为 type）。
- **构造无参**：`AddComponent` 内部 `compType()`，业务参数禁止入参，保证 Component 可在任意时刻挂载。

## 3. IComponent 生命周期契约

```
┌──────────────┐    AddComponent(T)     ┌──────────────────┐
│   未挂载      │ ─────────────────────▶ │ 已挂载（待初始化） │
└──────────────┘                        └────────┬─────────┘
                                                 │ InitAllComponents()
                                                 ▼
                                        ┌──────────────────┐
                                        │     运行中        │
                                        └────────┬─────────┘
                                                 │ RemoveComponent / Destroy
                                                 ▼
                                        ┌──────────────────┐
                                        │  OnDestroy 已回调 │
                                        └──────────────────┘
```

| 阶段 | 调用方 | 约束 |
|------|--------|------|
| `__init__()` | BaseAgent.AddComponent 内部 | 仅做字段默认值，不可访问其他 Component |
| `OnInitialize(agent)` | BaseAgent.InitAllComponents | 通过 `agent.GetComponent(...)` 注入依赖；可抛 RuntimeError 中断启动 |
| `OnDestroy()` | RemoveComponent / Destroy | 释放外部资源（子进程、文件句柄、后台任务） |

## 4. 组件间通信

**唯一规范**：Component 调用其他 Component 必须通过 `agent.GetComponent(TargetComponent)` 获取，**禁止**作为参数互传。

```python
# BAD：Component 作为参数传递
def DoSomething(self, sessionComponent: SessionComponent) -> None: ...

# GOOD：从 OnInitialize 注入并缓存
def OnInitialize(self, agent: BaseAgent) -> None:
    self._session = agent.GetComponent(SessionComponent)
```

理由：

- 调用链显式收敛于 OnInitialize，便于排查依赖关系。
- 同类型 Component 替换时无需修改 caller 签名。
- 防止跨 Agent 的 Component 串扰。

## 5. 组件注册顺序与依赖

[Agent.\_\_init\_\_](file:///c:/Users/Administrator/Desktop/Brain-main/agent/agent.py#L53-L80) 中的固定挂载顺序（顺序仅影响 OnInitialize 调用次序，不影响功能）：

```
1.  DataComponent       ← 配置 + LLM 句柄（最先，被多人依赖）
2.  LLMComponent        ← 依赖 DataComponent.llm
3.  SessionComponent    ← 依赖 MemoryComponent（可选注入）
4.  ContextComponent    ← 依赖 SessionComponent + LLMComponent + DataComponent
5.  RuleComponent       ← 无依赖
6.  SkillComponent      ← 无依赖
7.  McpComponent        ← 无依赖
8.  ToolComponent       ← 无依赖（使用类级注册表）
9.  HarnessComponent    ← 依赖以上全部，BuildAsync 阶段消费
10. LoggingComponent    ← 依赖 DataComponent + SessionComponent
```

依赖示意：

```
HarnessComponent ──▶ Context / Rule / Skill / Mcp / Tool / Data
ContextComponent ──▶ Session / LLM / Data
LLMComponent     ──▶ Data
SessionComponent ──▶ Memory (optional)
LoggingComponent ──▶ Data / Session
```

挂载完成后调用 `InitAllComponents()` 触发全量 OnInitialize；后续 [\_RunReActCoreAsync](file:///c:/Users/Administrator/Desktop/Brain-main/agent/agent.py#L199) 首轮调用 `HarnessComponent.BuildAsync()` 完成 LOD0 装填。

## 6. 四维调用接口

[BaseAgent](file:///c:/Users/Administrator/Desktop/Brain-main/agent/core/baseAgent.py) 不约束调用入口；具体的 [Agent](file:///c:/Users/Administrator/Desktop/Brain-main/agent/agent.py) 子类暴露四维入口：

| 方法 | 同步性 | 流式 | 实现路径 |
|------|--------|------|----------|
| `RunAsync` | async | 是 | `_RunReActCoreAsync(streaming=True)` |
| `RunInvokeAsync` | async | 否 | `_RunReActCoreAsync(streaming=False)` |
| `RunStream` | sync | 是 | `RunAsyncGenerator(RunAsync(...), timeout=runTimeout)` |
| `RunInvoke` | sync | 否 | `RunAsyncGenerator(RunInvokeAsync(...), timeout=runTimeout)` |

公共特性：

- 入参均为 `(userMessage: str, cancellationToken: Optional[CancellationToken])`。
- 出参均为 `Iterator/AsyncIterator[AgentStreamEvent]`。
- 顶层用 `_runLock`（asyncio.Lock）防止同 Agent 并发重入；惰性初始化避开同步构造时无事件循环的问题。
- 所有路径经过 [RunWithLifecycleAsync](file:///c:/Users/Administrator/Desktop/Brain-main/agent/agent.py#L168) 模板方法，确保 `AfterTurnAsync` + 日志刷盘在 finally 中执行。

## 7. EAgentState 状态机

定义见 [eAgentState.py](file:///c:/Users/Administrator/Desktop/Brain-main/agent/component/data/eAgentState.py)，`VALID_TRANSITIONS` 声明合法转移：

```
IDLE ─────▶ THINKING ─────▶ ACTING ─────▶ THINKING (循环)
                │              │
                ├─▶ FINISHED   ├─▶ FINISHED
                ├─▶ ERROR      └─▶ ERROR
                └─▶ WAITING_USER
WAITING_USER ─▶ THINKING / IDLE / ERROR
FINISHED / ERROR ─▶ IDLE / THINKING (复位)
```

实现要点：

- DataComponent.state setter 校验转移合法性，**非法仅警告**不阻断（避免破坏现有流程，便于排查）。
- 状态变更通过 `AgentStreamEvent.StateChange(newState, turn)` 流向调用方。
- WAITING_USER 当前为预留态，未在主循环启用。

## 8. SimpleAgent 简化版

[SimpleAgent](file:///c:/Users/Administrator/Desktop/Brain-main/agent/simpleAgent.py) 演示如何利用 BaseAgent 的组合能力构造极简 Agent：

```
SimpleAgent
  ├─ DataComponent   (持 LLM 句柄)
  └─ LLMComponent    (四维 LLM 调用)
```

特点：

- 无 ReAct、无工具、无 Context、无 Skill。
- `RunAsync` 直接调用 `_llmComp.StreamAsync` 返回单轮文本。
- 适合纯对话场景或作为新 Agent 子类的脚手架参考。

## 9. 关键文件索引

| 文件 | 职责 |
|------|------|
| [agent/core/baseAgent.py](file:///c:/Users/Administrator/Desktop/Brain-main/agent/core/baseAgent.py) | Entity 容器：组件字典 + 生命周期管理 |
| [agent/core/baseComponent.py](file:///c:/Users/Administrator/Desktop/Brain-main/agent/core/baseComponent.py) | IComponent 抽象基类与契约 |
| [agent/agent.py](file:///c:/Users/Administrator/Desktop/Brain-main/agent/agent.py) | ReAct 主编排器，四维入口 + 主循环 |
| [agent/simpleAgent.py](file:///c:/Users/Administrator/Desktop/Brain-main/agent/simpleAgent.py) | 纯对话 Agent 范例 |
| [agent/agentStreamEvent.py](file:///c:/Users/Administrator/Desktop/Brain-main/agent/agentStreamEvent.py) | 统一流事件结构 |
| [agent/component/data/](file:///c:/Users/Administrator/Desktop/Brain-main/agent/component/data) | 配置 + 状态机 + LLM 句柄 |
