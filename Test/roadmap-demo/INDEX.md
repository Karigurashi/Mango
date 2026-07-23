# Code Roadmap

面向模糊报障（如「结算挂了」）的模块导航索引。

用法：
1. 用描述匹配模块（aliases）
2. 仅在模块 `roots` 内 grep
3. 需要时再打开 `related` 模块

## 模块列表

- [[agent-core]] Agent 编排核心 — `agent, 编排, ReAct, Agent`
- [[agent-llm]] LLM 组件 — `llm, 模型, chat, LLMComponent`
- [[agent-tool]] 工具系统 — `工具, tool, grep, 文件工具, ToolComponent`
- [[settlement-demo]] 结算 — `结算, 清算, Settlement, Settle`

## Unity 提示

- 优先用 `.asmdef` 所在目录作为 `roots`
- 忽略 `Library/`、`Temp/`、`Logs/` 等生成目录
- 本 INDEX 可手写维护；`suggest-asmdef` 仅生成草稿建议

