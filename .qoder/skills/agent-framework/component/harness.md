# HarnessComponent 线束组件

Agent 启动时的装配总管：把内置工具、外部扩展（Rules/Skills/MCP）以及 LOD0 注入消息一次性"束"到一起。

## BuildAsync 装载流程

```
BuildAsync(reloadExtensions=True) → int（返回 System 块数量）
├─ 幂等检查：_built=True → return 0
├─ _ReloadExtensions():
│   ruleComp.Clear() + LoadFromDirectory
│   skillComp.Clear() + LoadFromDirectory
│   mcpComp.Clear() + LoadFromMCPJson
├─ LOD0 注入（顺序固定）：
│   1. Memory.LoadContextBlocks()          # INDEX.md
│   2. ruleComp.GetAlwaysApplyBody()       # ALWAYS_APPLY 规则
│   3. skillComp.GetAllPrefixes()          # 技能前缀清单
│   4. mcpComp.GetToolDescriptions()       # MCP 描述
├─ Skill 工具注入：Count() > 0 → RegisterTool(LoadSkillTool)
├─ MCP 连接：tools = await ConnectAllAsync() → 逐个 RegisterTool
├─ 工具绑定：llmComp.BindTools(toolComp.GetAllToolSpecs())
└─ _built = True
```

## LOD0 注入顺序

注入顺序固定，决定模型每轮 system 块结构：

| 顺序 | 来源 | 内容 |
|------|------|------|
| 1 | Memory | INDEX.md 导航索引 |
| 2 | Rules | ALWAYS_APPLY Rule 全文 |
| 3 | Skills | `<available_skills>` + 前缀清单 |
| 4 | MCP | `<mcp_servers>` + 工具描述 |

## 关键设计

- **_built 幂等保护**：已构建返回 0，避免重复创建 MCP 子进程和重复注册工具。
- **_ReloadExtensions 先 Clear 再 Load**：保证热更时旧扩展被清除。
- **BindTools 一次绑齐**：整个 Run 期间 LLM 工具列表稳定。
- **OnDestroy 重置 _built = False**：允许重建恢复装载能力。
