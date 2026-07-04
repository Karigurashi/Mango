# DataComponent 数据与配置

Agent 的配置/状态/LLM 实例的唯一权威。第一个挂载、最后一个销毁。任何组件需要配置或状态时都通过 `agent.GetComponent(DataComponent)` 反查。

## AgentConfig 聚合配置

三层子配置组合：

```
AgentConfig
├── loop: AgentLoopConfig       # ReAct循环 + 路径配置
├── context: ContextConfig      # Token预算 + 压缩参数
└── persist: PersistConfig      # 工具结果落盘 + 外存管理
```

### AgentLoopConfig

控制 ReAct 循环行为与运行时路径。关键字段：maxTurns（默认25）、autoCompact（默认True）、workspaceRoot / skillsDir / rulesDir / mcpJsonPath / memoryDir。

### ContextConfig

Token 预算与压缩参数。关键字段：maxTokens（128000）、reserveTokens（4096）、compactThreshold（0.85）、keepRecentTurns（5）、coldOffloadGraceSeconds（300）、autoColdOffload（True）。

派生属性 `effectiveBudget`：`loop.tokenBudget > 0 ? loop.tokenBudget : maxTokens - reserveTokens`。

### PersistConfig

大结果落盘参数：persistCharThreshold（5000）、persistPreviewChars（500）、storeMaxTotalSize（50MB）、storeMaxFileCount（10）。

### 校验

DataComponent.OnInitialize 调用 `config.Validate()` 聚合所有子配置校验，配置错误启动期立刻报错。

## EAgentState 状态机

```
IDLE → THINKING ↔ ACTING
         ↓          ↓
      FINISHED ←───┘
         ↓
       ERROR
```

| 值 | 含义 |
|----|------|
| IDLE | 初始 / Run 结束后 |
| THINKING | 正在调 LLM |
| ACTING | 正在执行工具 |
| FINISHED | Run 正常终止 |
| ERROR | Run 因异常终止 |

DataComponent.state setter 校验转移合法性。非法转移仅 Warning 不阻断——保证 ReAct 主循环不被状态机 corner case 打断。

## 关键设计

- **配置 OnInitialize 后视为冻结**：所有组件持有 AgentConfig 引用，运行时改字段破坏可重入性，通过约定禁止。
- **LLM 单实例**：整个 Agent 生命周期只持有一个 BaseLLM，跨组件共享。
- **状态机宽容**：非法转移不抛异常，仅记录。
