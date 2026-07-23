"""Agent 运行时统一配置 —— 单一扁平 dataclass。

按功能域分组，所有字段均为不可变类型（int/float/bool/str/NoneType）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from common.const import ERoad


# ---- 内置默认压缩 Prompt ----

DEFAULT_BATCH_SUMMARY_PROMPT = (
    "Your task is to create a detailed summary of the conversation so far, "
    "paying close attention to the user's explicit requests and your previous actions. "
    "This summary should be thorough in capturing technical details, code patterns, "
    "and architectural decisions that would be essential for continuing development work without losing context.\n\n"
    "Before providing your final summary, wrap your analysis in <analysis> tags "
    "to organize your thoughts and ensure you've covered all necessary points. "
    "In your analysis process:\n\n"
    "1. Chronologically analyze each message and section of the conversation. "
    "For each section thoroughly identify:\n"
    "- The user's explicit requests and intents\n"
    "- Your approach to addressing the user's requests\n"
    "- Key decisions, technical concepts and code patterns\n"
    "- Specific details like: file names, full code snippets, function signatures, file edits\n"
    "- Errors that you ran into and how you fixed them\n"
    "- Pay special attention to specific user feedback that you received, "
    "especially if the user told you to do something differently.\n\n"
    "2. Double-check for technical accuracy and completeness, "
    "addressing each required element thoroughly.\n\n"
    "Your summary should include the following sections:\n\n"
    "1. Primary Request and Intent: Capture all of the user's explicit requests and intents in detail\n"
    "2. Key Technical Concepts: List all important technical concepts, technologies, and frameworks discussed.\n"
    "3. Files and Code Sections: Enumerate specific files and code sections examined, modified, or created. "
    "Pay special attention to the most recent messages and include full code snippets where applicable "
    "and include a summary of why this file read or edit is important.\n"
    "4. Errors and fixes: List all errors that you ran into, and how you fixed them. "
    "Pay special attention to specific user feedback that you received, "
    "especially if the user told you to do something differently.\n"
    "5. Problem Solving: Document problems solved and any ongoing troubleshooting efforts.\n"
    "6. All user messages: List ALL user messages that are not tool results. "
    "These are critical for understanding the users' feedback and changing intent.\n"
    "7. Pending Tasks: Outline any pending tasks that you have explicitly been asked to work on.\n"
    "8. Current Work: Describe in detail precisely what was being worked on immediately before this summary request, "
    "paying special attention to the most recent messages from both user and assistant. "
    "Include file names and code snippets where applicable.\n"
    "9. Optional Next Step: List the next step related to the most recent work, "
    "only if directly in line with the user's latest explicit request. "
    "Include verbatim quotes from the conversation showing where you left off.\n\n"
    "Please provide your summary based on the conversation so far, "
    "following this structure and ensuring precision and thoroughness in your response."
)


@dataclass
class AgentConfig:
    """Agent 运行时统一配置。
    
    按功能域分组的扁平 dataclass，所有字段均为不可变类型。
    """
    
    # -- 循环行为 --
    maxTurns: int = 99                      # 单次 Run 最大推理轮次，-1 表示无限制
    tokenBudget: int = 0                    # ContextComponent 组装预算（0 则用 maxTokens - reserveTokens）
    runTimeout: float = 0.0                 # 单次 Run 最大执行秒数，0 表示不限
    
    # -- 路径配置 --
    workspaceRoot: str = str(ERoad.WORKSPACE)           # 工作区根目录
    skillsDir: str = str(ERoad.SKILLS_DIR)              # Skill 扫描目录（**/SKILL.md）
    rulesDir: str = str(ERoad.RULES_DIR)                # Rule 扫描目录（.md / .mdc）
    mcpJsonPath: str = str(ERoad.MCP_JSON_PATH)         # MCP 配置文件路径（.mcp.json）
    memoryDir: str = str(ERoad.MEMORY_DIR)              # 记忆持久化目录
    tasksDir: str = str(ERoad.TASKS_DIR)                # 定时任务 JSON 目录
    mangoIgnorePath: str = str(ERoad.MANGO_IGNORE)       # .mangoIgnore 自定义忽略文件路径（gitignore 语义）
    
    # -- Token 预算 --
    maxTokens: int = 200000                # Token 预算上限
    reserveTokens: int = 4096              # 为模型回复预留的 token 数
    
    # -- 压缩参数 --
    compactThreshold: float = 0.85         # 触发压缩的上下文占用率阈值（0.0-1.0）
    keepRecentTurns: int = 3               # 压缩时保留的最近完整轮数
    coldOffloadGraceSeconds: int = 600     # 冷卸载宽限期（秒）
    autoColdOffload: bool = True           # 是否在每轮用户对话前自动冷卸载（True 开启）
    summaryMaxTokens: int = 1024           # 单条消息摘要 LLM 最大输出 token
    batchSummaryMaxTokens: int = 8192      # 批量压缩摘要 LLM 最大输出 token
    compactionPrompt: str | None = None    # LLM 压缩时的自定义 prompt（None 则用内置默认）
    
    # -- 落盘参数 --
    enablePersist: bool = True             # 是否启用大结果落盘+预览
    persistCharThreshold: int = 50000      # 触发落盘的字符数阈值
    persistPreviewChars: int = 5000        # 预览截断字符数
    storeDir: str = str(ERoad.STORE_PATH)    # 内容外存目录
    storeMaxTotalSize: int = 500 * 1024 * 1024       # 外存目录总容量上限（超限LRU淘汰，默认50MB）
    storeMaxFileCount: int = 100           # 外存目录最大文件数（超限LRU淘汰，默认100）
    
    # -- 子系统开关 --
    enableWorkflow: bool = False            # 是否启用 Workflow 子系统（开启后注入 run_workflow 等编排工具）
    enableSchedule: bool = False            # 是否启用定时任务子系统（开启后注入 createTask / deleteTask 工具）

    # -- 外部密钥 --
    tavilyApiKey: str = ""  # Tavily Search API 密钥

    # ---- 属性 ----

    @property
    def effectiveBudget(self) -> int:
        """实际可用于上下文组装的 token 预算。

        tokenBudget > 0 时直接使用，否则按 maxTokens - reserveTokens 计算。
        """
        if self.tokenBudget > 0:
            return self.tokenBudget
        return self.maxTokens - self.reserveTokens


# 默认配置单例（每次 copy 使用，避免共享修改）
AgentConfig.DEFAULT = AgentConfig()
