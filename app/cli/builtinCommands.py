"""内置斜杠指令 —— 注册 /help /clear /compact /model /cost /status 等 11 个指令。

RegisterBuiltinCommands() 函数将全部内置指令注册到 CliCommandRegistry。
"""

from __future__ import annotations

from agent.component.tool.eToolCategory import EToolCategory
from llm import LLMManager

from .cliCommand import CliCommand, CliContext
from .cliCommandRegistry import CliCommandRegistry


def RegisterBuiltinCommands(registry: CliCommandRegistry) -> None:
    """注册全部内置指令到 registry。"""
    registry.Register(CliCommand("help", "Show available commands", _HelpAsync, aliases=["h"]))
    registry.Register(CliCommand("clear", "Clear conversation history", _ClearAsync, aliases=["c"]))
    registry.Register(CliCommand("compact", "Trigger context compaction", _CompactAsync))
    registry.Register(CliCommand("model", "List or switch model", _ModelAsync, aliases=["m"]))
    registry.Register(CliCommand("cost", "Show token usage", _CostAsync))
    registry.Register(CliCommand("status", "Show agent status", _StatusAsync, aliases=["s"]))
    registry.Register(CliCommand("sessions", "List sessions", _SessionsAsync))
    registry.Register(CliCommand("session", "Save session to file", _SessionAsync))
    registry.Register(CliCommand("tools", "List registered tools", _ToolsAsync, aliases=["t"]))
    registry.Register(CliCommand("config", "Show agent configuration", _ConfigAsync))
    registry.Register(CliCommand("reload", "Rebuild harness (reload rules/skills/MCP tools)", _ReloadAsync))
    registry.Register(CliCommand("exit", "Exit CLI", _ExitAsync, aliases=["quit", "q"]))


# ==================== /help ====================

async def _HelpAsync(ctx: CliContext, args: str) -> None:
    """打印所有可用指令及描述。"""
    ctx.Print("Available commands:")
    ctx.PrintDim(ctx.Registry.GetHelpText())


# ==================== /clear ====================

async def _ClearAsync(ctx: CliContext, args: str) -> None:
    """创建新会话，清空对话历史。"""
    newId = ctx.Session.NewSession()
    ctx.Print(f"Conversation cleared. New session: #{newId}")
    ctx.PrintDim("System rules and skills are preserved.")


# ==================== /compact ====================

async def _CompactAsync(ctx: CliContext, args: str) -> None:
    """手动触发上下文压缩。"""
    ctx.PrintDim("Compacting context...")
    tokenSaved = await ctx.Context.CompactAsync(force=True)
    if tokenSaved > 0:
        ctx.Print(f"Compaction freed {tokenSaved} tokens.")
    else:
        ctx.PrintDim("Compaction not required (within budget).")


# ==================== /model ====================

async def _ModelAsync(ctx: CliContext, args: str) -> None:
    """列出可用模型或切换到指定模型。

    /model            → 列表
    /model <name>     → 切换
    """
    modelName = args.strip()
    if not modelName:
        _PrintModelList(ctx)
        return

    try:
        newLlm = LLMManager.GetProvider(modelName)
    except KeyError:
        ctx.PrintError(
            f"Unknown model: {modelName}. Available: {', '.join(LLMManager.ListModels())}"
        )
        return

    dataComp = ctx.Data
    dataComp.llm = newLlm
    ctx.LLM.llm = newLlm
    ctx.Print(f"Switched to {modelName} ({newLlm.modelName})")


def _PrintModelList(ctx: CliContext) -> None:
    """打印可用模型列表，标记当前模型。"""
    current = ctx.LLM.modelName
    models = LLMManager.ListModels()
    ctx.PrintDim("Available Models:")
    for name in models:
        llm = LLMManager.GetProvider(name)
        marker = "*" if llm.modelName == current else " "
        ctx.Print(f" {marker} {name}  ({llm.modelName})")
    ctx.PrintDim("Use /model <name> to switch.")


# ==================== /cost ====================

async def _CostAsync(ctx: CliContext, args: str) -> None:
    """显示 Token 用量统计。"""
    llm = ctx.LLM
    cfg = ctx.Config
    ctx.Print("Token Usage:")
    ctx.PrintDim(f"  Input:      {cfg.FormatK(llm.TotalPromptTokens)}")
    ctx.PrintDim(f"  Output:     {cfg.FormatK(llm.TotalCompletionTokens)}")
    ctx.PrintDim(f"  Total:      {cfg.FormatK(llm.TotalPromptTokens + llm.TotalCompletionTokens)}")
    ctx.PrintDim(f"  Cache Hit:  {llm.LastCacheHitRate:.1f}%")


# ==================== /status ====================

async def _StatusAsync(ctx: CliContext, args: str) -> None:
    """显示 Agent 运行时状态。"""
    session = ctx.Session
    llm = ctx.LLM

    ctx.Print("Agent Status:")
    ctx.PrintDim(f"  State:        {ctx.Data.state.name}")
    ctx.PrintDim(f"  Model:        {llm.modelName} ({llm.providerName})")
    ctx.PrintDim(f"  Session:      #{session.ActiveSessionId} ({session.GetMessageCount()} messages)")
    ctx.PrintDim(f"  Est. Tokens:  {ctx.Config.FormatK(llm.LastPromptTokens)}")
    ctx.PrintDim(f"  Tools:        {ctx.Tools.Count()} registered")


# ==================== /sessions ====================

async def _SessionsAsync(ctx: CliContext, args: str) -> None:
    """列出所有会话，标记活跃。"""
    activeId = ctx.Session.ActiveSessionId
    ids = ctx.Session.GetSessionIds()
    ctx.PrintDim(f"Sessions ({len(ids)}):")
    for sid in sorted(ids):
        marker = "*" if sid == activeId else " "
        session = ctx.Session.GetSession(sid)
        count = session.GetMessageCount() if session else 0
        ctx.PrintDim(f" {marker} #{sid} ({count} messages)")
    ctx.PrintDim("Use /session to save current session.")


# ==================== /session ====================

async def _SessionAsync(ctx: CliContext, args: str) -> None:
    """将当前 session 以人类可读 Markdown 格式写入 memory/sessions/YYYY-MM-DD/{sessionId}.md。"""
    count = ctx.Session.SaveToMarkdown()
    if count > 0:
        ctx.Print(f"Session saved ({count} messages)")
    else:
        ctx.PrintError("No active session or save failed.")


# ==================== /tools ====================

async def _ToolsAsync(ctx: CliContext, args: str) -> None:
    """按分类列出已注册工具。"""
    tools = ctx.Tools.GetAll()
    if not tools:
        ctx.PrintDim("No tools registered.")
        return

    # 按 EToolCategory 分组
    categories: dict[EToolCategory, list[dict]] = {}
    for name, tool in tools.items():
        cat = tool.category
        if cat not in categories:
            categories[cat] = []
        categories[cat].append({"name": name, "desc": tool.description})

    ctx.PrintDim(f"Registered Tools ({len(tools)}):")
    for cat in sorted(categories, key=lambda c: c.name):
        ctx.Print(f"  {cat.name}:")
        for t in categories[cat]:
            ctx.PrintDim(f"    {t['name']}  - {t['desc']}")


# ==================== /config ====================

async def _ConfigAsync(ctx: CliContext, args: str) -> None:
    """显示当前 Agent 配置。"""
    dataComp = ctx.Data
    config = dataComp.config

    ctx.Print("Agent Configuration:")
    ctx.PrintDim(f"  Workspace Root: {config.workspaceRoot}")
    ctx.PrintDim(f"  Max Turns:      {config.maxTurns}")
    ctx.PrintDim(f"  Token Budget:   {ctx.Config.FormatK(config.effectiveBudget)}")
    ctx.PrintDim(f"  Auto ColdOffload: {config.autoColdOffload}")
    ctx.PrintDim(f"  Persist Enable: {config.enablePersist}")
    ctx.PrintDim(f"  Skills Dir:     {config.skillsDir}")
    ctx.PrintDim(f"  Rules Dir:      {config.rulesDir}")


# ==================== /reload ====================

async def _ReloadAsync(ctx: CliContext, args: str) -> None:
    """重建 harness：重载 rules / skills / MCP 工具配置并重新绑定到 LLM。"""
    ctx.PrintDim("Rebuilding harness...")
    try:
        await ctx.Harness.BuildAsync(force=True)
        toolCount = ctx.Tools.Count()
        ctx.Print(f"Harness rebuilt ({toolCount} tools registered).")
    except Exception as exc:
        ctx.PrintError(f"Harness rebuild failed: {exc}")


# ==================== /exit ====================

async def _ExitAsync(ctx: CliContext, args: str) -> None:
    """退出 CLI。"""
    ctx.RequestExit()
