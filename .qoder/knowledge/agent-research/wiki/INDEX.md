# AI Agent 框架研究

最后编译: 2026-05-31 16:14:53

概念总数: 24


## 概念索引


| 概念 | 摘要 | 分类 | 置信度 |

|------|------|------|--------|

| [[Agent Configuration]] | Agent 配置即代码模式，通过 AGENTS.md 定义行为约束和操作规则，S | Agent配置 | high |

| [[Agent Memory]] | 持久化存储对话历史、实体记忆和知识图谱，结合状态持久化与可观测性，为 Agent | Agent基础设施 | high |

| [[Channel Abstraction]] | 将输入/输出通道抽象为独立可插拔组件，分离通道协议与 Agent 业务逻辑，支持 | Agent基础设施 | high |

| [[Dynamic Planning Pattern]] | 在执行过程中根据中间结果动态调整后续计划，克服静态计划的僵化，提高对不确定环境的 | Agent架构 | medium |

| [[Gateway Architecture]] | Gateway（网关）作为控制平面，负责接收多通道输入、路由到对应 Agent/ | Agent架构 | high |

| [[Graph-based Agents]] | 基于有向图的工作流引擎（如 LangGraph），通过 State、Nodes、 | Agent架构 | high |

| [[Hierarchical Agents]] | 树形层级结构：顶层监督者分解任务并作为中央编排器，中间层管理者协调，底层工作者执 | Agent架构 | high |

| [[Hub-and-Spoke Agents]] | 中心 Gateway 作为控制平面，将用户输入请求路由到对应的 Agent 或  | Agent架构 | high |

| [[Human-in-the-Loop]] | Agent 在关键节点（如审批门）暂停执行，通知人类操作员提供建议动作、推理和上 | Agent架构 | high |

| [[Hybrid Architectures]] | 按需组合层级编排、并行执行、人机协同等多种模式，并利用框架原生的 Human-i | Agent架构 | high |

| [[MCP Protocol]] | Model Context Protocol（MCP）是 Anthropic 提 | Agent协议 | high |

| [[Multi-Agent Collaboration]] | 多个 Agent 通过任务分解、信息共享和结果聚合协同完成复杂任务，支持层级、并 | Agent架构 | high |

| [[Parallel Agents]] | 多个 Agent 同时独立执行子任务，通过任务分解和结果聚合加速处理，适用于可并 | Agent架构 | high |

| [[Plan and Solve Pattern]] | 先制定完整计划再逐步执行，将复杂问题分解为可管理的子步骤，提高任务完成的准确性和 | Agent架构 | high |

| [[ReAct Pattern]] | 思考（Reasoning）→ 行动（Acting）→ 观察（Observatio | Agent架构 | high |

| [[Reflection Pattern]] | Agent 对自身输出进行自我检查和修正，通过多轮反思提高回答质量和准确性。 | Agent架构 | high |

| [[Sequential Agents]] | 多个 Agent 按顺序流水线执行，前一个 Agent 的输出作为后一个 Age | Agent架构 | high |

| [[Single Agent + MCP Servers + Tools]] | 单个 Agent 通过 MCP 协议连接多个工具服务器，实现标准化、可扩展的工具 | Agent架构 | high |

| [[Single Agent + Tools]] | 单个 Agent 直接调用内置或自定义工具（如文件读写、Shell 执行、代码搜 | Agent架构 | high |

| [[Skill System]] | 将 Agent 能力封装为可复用的技能模块，支持动态加载、组合和版本管理，实现能 | Agent基础设施 | high |

| [[Swarm Agents]] | 去中心化的多 Agent 群体协作模式，Agent 之间通过消息传递和任务广播协 | Agent架构 | high |

| [[Task-Decoupled Planning Pattern]] | 将任务规划与执行分离，规划器负责制定计划，执行器负责按计划执行，提高系统的模块化 | Agent架构 | medium |

| [[Tool Use Pattern]] | Agent 通过工具调用与外部世界交互，工具封装了文件系统、Shell 执行、A | Agent架构 | high |

| [[Tree of Thoughts Pattern]] | 探索多条推理路径的树状结构，Agent 在决策点分叉出多个思考分支，通过评估和回 | Agent架构 | medium |
