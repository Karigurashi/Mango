# Claude Code Agent SDK 架构（2026）

来源: AnyCap "Claude Code Agent SDK 完整开发者指南 2026"

## 概述

Anthropic 于 2026 年初发布，将 Claude Code CLI 的 Agent 循环、工具系统和沙箱执行环境封装为可编程 SDK（Python/TypeScript）。

## Claude API vs Agent SDK

| 功能 | Claude API | Agent SDK |
|------|-----------|-----------|
| Agent 循环 | 自己构建 | 内置：规划→执行→观察→重复 |
| 文件系统访问 | 无 | 读取、写入、编辑文件 |
| Shell 执行 | 无 | 沙箱中执行 Bash |
| 工具调用 | 手动定义函数 | 内置工具 + MCP 服务器支持 |
| 子代理 | 不可用 | 可启动并行代理工作线程 |
| 上下文管理 | 手动 | 自动压缩与摘要 |

## 核心概念

### Agent 循环
```
任务 → 规划 → 工具调用 → 观察结果 → 重新规划 → ... → 最终答案
```
每次迭代: Claude 决定下一步 → 调用工具 → 接收输出 → 决定继续或结束。

### 内置工具
`read`, `write`, `edit`, `glob`, `grep`, `bash`, `task`（子代理启动）。

### 自定义工具（@tool 装饰器）
定义函数签名 + 描述 → Agent 自动决定何时调用。

### 子代理（并行处理）
`task` 工具可启动独立 Claude 实例并行工作，隔离上下文中运行，独立返回结果。

### MCP 服务器集成
SDK 原生支持 Model Context Protocol 服务器，可扩展数据库、API、第三方服务。

## 生产环境考量

- **上下文管理**: 超过 100 轮的长生命周期 Agent 需用子代理并行处理
- **成本**: 典型会话 $0.50-$3.00；设置 max_turns 防止无限循环；简单任务用 Haiku，主任务用 Sonnet
- **安全**: ALLOWED_DIRECTORIES 限制文件访问；禁止访问凭证文件；非交互模式审查动作

## 五大能力缺口

1. 图像生成 — 不能直接生成或查看图像
2. 视频生成 — 不能生成视频内容
3. 带依据的网页搜索 — 无语义搜索+引用
4. 云存储与文件共享 — 文件访问仅限本地
5. 发布与部署 — 无内置部署能力

## Claude Code SDK vs Claude Agent SDK

| | Claude Code SDK | Claude Agent SDK |
|---|---|---|
| 范围 | 较低层 API | 更高层 Agent 框架 |
| 场景 | 程序化控制 Claude Code 会话 | 构建自治 Agent |

经验法则：输入命令用 CLI，编写调用 Claude 的代码用 SDK。
