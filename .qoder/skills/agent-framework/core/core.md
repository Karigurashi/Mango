# Core 核心基座层

> 源码：[`agent/core/baseAgent.py`](../../../agent/core/baseAgent.py)、[`agent/core/baseComponent.py`](../../../agent/core/baseComponent.py)

Core 层是 Brain Agent 框架的最底层抽象，**零业务逻辑**，只提供 Unity 风格 Entity-Component 的容器与组件契约。所有上层 Agent（Agent / SimpleAgent / 用户自定义 Agent）都直接复用这两个类，组件之间的解耦正是建立在它们之上。

## 1 模块结构

```
agent/core/
├── baseAgent.py        # Entity 容器：组件挂载 / 查找 / 初始化 / 销毁
└── baseComponent.py    # Component 抽象基类：生命周期契约
```

## 2 IComponent 接口契约（baseComponent.py）

`IComponent` 是所有组件的抽象父类，规定了与容器交互的最小协议。

| 成员 | 签名 | 角色 |
|------|------|------|
| `__init__` | `def __init__(self) -> None` | **MUST 无参** —— 业务参数只能通过 `OnInitialize` 注入 |
| `OnInitialize` | `def OnInitialize(self, agent: BaseAgent) -> None` | 容器调用，在所有组件添加完成后执行；此时可通过 `agent.GetComponent` 获取兄弟组件 |
| `OnDestroy` | `def OnDestroy(self) -> None` | 容器销毁时回调，用于释放外部资源（子进程 / 文件句柄 / 后台 Task） |
| `_initialized` | `bool` | 私有标志，由 `BaseAgent.InitAllComponents` 维护，保证幂等 |
| `IsInitialized` | `@property -> bool` | 只读暴露，便于断言 |

> **设计约束**：构造函数 **不允许**接收业务参数（DataComponent 例外，由全局唯一配置桥接）。这一约束保证了组件可以被 `AddComponent[T]()` 用纯类型注册——容器无需理解组件内部依赖。

## 3 BaseAgent 容器（baseAgent.py）

`BaseAgent` 是 Entity-Component 模式中的 **Entity**，持有一组互不感知的 `IComponent`，并暴露统一的添加 / 查询 / 销毁入口。

### 3.1 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `_components` | `Dict[Type[IComponent], IComponent]` | 类型即键，**O(1) 查找**，同类型组件唯一 |
| `_initialized` | `bool` | 容器级初始化标志，防止重复执行 `OnInitialize` |
| `_destroyed` | `bool` | 容器级销毁标志，幂等保护 |

### 3.2 关键方法

```text
AddComponent[T extends IComponent](self) -> T
    │
    ├─ 已存在 T 实例 ──► 返回旧实例（不重复创建）
    └─ 新建 T()       ──► 写入 _components[T]，返回新实例
                        ※ 若已 _initialized=True，立即调用其 OnInitialize

GetComponent[T extends IComponent](self) -> T | None
    │
    └─ 直接返回 _components.get(T)（O(1)）

InitAllComponents(self)
    │
    ├─ 已 _initialized ──► 直接 return（幂等）
    └─ 遍历 _components ──► 跳过已 _initialized 的组件，逐一 OnInitialize
                          完成后置位 _initialized=True

Destroy(self)
    │
    ├─ 已 _destroyed ──► 直接 return（幂等）
    └─ 倒序遍历 _components.values() ──► 调用 OnDestroy（异常仅记录不抛出）
                                       清空 _components，置 _destroyed=True
```

### 3.3 初始化时序

容器外部典型用法（Agent 子类构造里）：

```text
agent = Agent(config)
  ├─ self.AddComponent(DataComponent)
  ├─ self.AddComponent(LLMComponent)
  ├─ … 其他组件 …
  └─ self.InitAllComponents()   # 一次性触发全部 OnInitialize
```

> **关键设计点**：**创建** 与 **初始化** 显式分离。所有组件都已挂载后才统一 `OnInitialize`，使任意组件的 `OnInitialize` 可以安全地通过 `agent.GetComponent[X]()` 反查兄弟组件，无需关心挂载顺序导致的"前向引用未注册"问题。

## 4 设计决策

| 决策 | 动机 |
|------|------|
| Type 作为键而非字符串 | 避免重名冲突；编译期类型推断；IDE 跳转友好 |
| `_components` 字典而非 list | `GetComponent` O(1)；同类型唯一约束自然成立 |
| 构造无参 + 延迟初始化 | 解耦组件挂载顺序，OnInitialize 时全部组件都已就绪 |
| `OnDestroy` 倒序回调 | 与挂载顺序对偶，下层依赖在上层消费方释放后再回收 |
| 容器零业务知识 | 同一套 BaseAgent 同时支撑 Agent / SimpleAgent / 测试 Mock，无 if/else |

## 5 与上层模块的关系

| 上层 | 通过 Core 获得的能力 |
|------|---------------------|
| `Agent` / `SimpleAgent` | 直接继承 `BaseAgent`，在 `__init__` 内 AddComponent 完成所有组件挂载 |
| 各 Component | 继承 `IComponent`，在 `OnInitialize` 内通过 `agent.GetComponent[X]()` 拉取依赖 |
| 测试用例 | 用 `BaseAgent` 直接挂载 Mock Component，无需 patch 框架其他部分 |

## 6 不变式（Invariants）

1. 同一 `BaseAgent` 实例下，**同类型组件唯一**。
2. `OnInitialize` 在每个组件实例上**至多被调用一次**。
3. `Destroy` 完成后再次调用 `Destroy` 不抛异常（幂等）。
4. `OnInitialize` 期间 `agent.GetComponent` 返回的实例 **必然已经 `__init__`**，但**不保证已 `OnInitialize`**（取决于挂载顺序）；如需要"已初始化"前提，组件应在 `OnInitialize` 内只持有引用、在首次业务调用时再做按需初始化。
