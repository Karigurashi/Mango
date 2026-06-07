# OpenClaw 架构设计（2025-2026）

来源: Towards AI "OpenClaw Architecture Deep Dive", LinkedIn 社区分析, Valletta Software Guide 2026

OpenClaw 是一个个人 AI Agent 框架，核心洞察：个人 AI Agent 是一个"个人操作系统"，而非又一个聊天机器人。

## Hub-and-Spoke 架构

中心是一个 Gateway（网关），作为控制平面：
- 用户输入（WhatsApp、Telegram、Slack、Web）→ Gateway
- Gateway → 路由到对应的 Agent/技能/Skill
- Agent 执行 → 结果路由回用户

## 核心设计原则

### 1. Agentic Loop（Agent 循环）
标准的 感知→推理→行动→观察 循环，但 OpenClaw 将其外化为显式的架构层。

### 2. Tool System（工具系统）
工具是可被发现和调用的能力单元。每个工具有明确的 schema、权限级别、执行沙箱。

### 3. Channel Abstraction（通道抽象）
输入/输出通道是独立可插拔的：WhatsApp、Telegram、Slack、Web、API 等。每个通道有独立的消息格式、速率限制和安全策略。

### 4. Skill System（技能系统）
Skill 是 Agent 的可复用能力包，包含：
- 提示词/指令
- 工具集
- 权限配置
- 执行约束

### 5. AGENTS.md / SOUL.md
- AGENTS.md: 定义 Agent 的行为、约束和操作规则
- SOUL.md: 定义 Agent 的"人格"、语气和价值观

## 架构层次

```
┌─────────────────────────────────┐
│        Channels (输入输出)        │
│  WhatsApp  Telegram  Slack  Web  │
├─────────────────────────────────┤
│          Gateway (路由)           │
├─────────────────────────────────┤
│       Agent Loop (执行引擎)       │
│  感知 → 推理 → 工具调用 → 观察    │
├─────────────────────────────────┤
│    Skills + Tools (能力层)       │
├─────────────────────────────────┤
│    Memory + State (持久化)       │
└─────────────────────────────────┘
```

## 关键教训

1. **分离通道与逻辑**: 输入通道的变化不应影响 Agent 核心逻辑
2. **显式权限模型**: 每个 Skill 有独立的权限边界，高风险操作需审批
3. **可观测性优先**: 每一步 Agent 决策和工具调用都应可追踪
4. **配置即代码**: AGENTS.md 和 SOUL.md 是版本控制的一部分
