"""Agent 运行时统一配置 —— 单一扁平 dataclass。

按功能域分组，所有字段均为不可变类型（int/float/bool/str/tuple/NoneType），
因此 copy.copy() 浅拷贝等价于 copy.deepcopy()，但性能更优。
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
import copy
from pickle import TRUE

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
    
    # -- Token 预算 --
    maxTokens: int = 128000                # Token 预算上限
    reserveTokens: int = 4096              # 为模型回复预留的 token 数
    
    # -- 压缩参数 --
    compactThreshold: float = 0.85         # 触发压缩的上下文占用率阈值（0.0-1.0）
    keepRecentTurns: int = 3               # 压缩时保留的最近完整轮数
    coldOffloadGraceSeconds: int = 300     # 冷卸载宽限期（秒）
    autoColdOffload: bool = True           # 是否在每轮用户对话前自动冷卸载（True 开启）
    summaryMaxTokens: int = 1024           # 单条消息摘要 LLM 最大输出 token
    batchSummaryMaxTokens: int = 8192      # 批量压缩摘要 LLM 最大输出 token
    compactionPrompt: str | None = None    # LLM 压缩时的自定义 prompt（None 则用内置默认）
    
    # -- 落盘参数 --
    enablePersist: bool = True             # 是否启用大结果落盘+预览
    persistCharThreshold: int = 25000      # 触发落盘的字符数阈值
    persistPreviewChars: int = 5000        # 预览截断字符数
    storeDir: str = str(ERoad.STORE_PATH)    # 内容外存目录
    storeMaxTotalSize: int = 50 * 1024 * 1024       # 外存目录总容量上限（超限LRU淘汰，默认50MB）
    storeMaxFileCount: int = 100           # 外存目录最大文件数（超限LRU淘汰，默认100）
    
    # -- 子系统开关 --
    enableWorkflow: bool = False            # 是否启用 Workflow 子系统（开启后注入 run_workflow 等编排工具）

    # -- 外部密钥 --
    tavilyApiKey: str = "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"  # Tavily Search API 密钥

    # ---- 属性 ----

    @property
    def effectiveBudget(self) -> int:
        """实际可用于上下文组装的 token 预算。

        tokenBudget > 0 时直接使用，否则按 maxTokens - reserveTokens 计算。
        """
        if self.tokenBudget > 0:
            return self.tokenBudget
        return self.maxTokens - self.reserveTokens

    @property
    def tavilyApiKeyResolved(self) -> str:
        """解析 Tavily API Key，优先环境变量 TAVILY_API_KEY。"""
        import os
        return os.environ.get("TAVILY_API_KEY", self.tavilyApiKey)

    # ---- 校验 ----

    def Validate(self) -> list[str]:
        """校验所有配置字段，返回错误信息列表。"""
        errors: list[str] = []

        # 循环行为
        if self.maxTurns < -1 or self.maxTurns == 0:
            errors.append(f"maxTurns must be > 0 or -1 (unlimited), got {self.maxTurns}")
        if self.tokenBudget < 0:
            errors.append(f"tokenBudget must be >= 0, got {self.tokenBudget}")
        if self.runTimeout < 0:
            errors.append(f"runTimeout must be >= 0, got {self.runTimeout}")

        # Token 预算
        if self.maxTokens <= 0:
            errors.append(f"maxTokens must be > 0, got {self.maxTokens}")
        if self.reserveTokens < 0:
            errors.append(f"reserveTokens must be >= 0, got {self.reserveTokens}")
        if self.reserveTokens >= self.maxTokens:
            errors.append(
                f"reserveTokens ({self.reserveTokens}) must be < maxTokens ({self.maxTokens})"
            )

        # 压缩参数
        if not (0.0 <= self.compactThreshold <= 1.0):
            errors.append(
                f"compactThreshold must be in [0.0, 1.0], got {self.compactThreshold}"
            )
        if self.keepRecentTurns < 0:
            errors.append(f"keepRecentTurns must be >= 0, got {self.keepRecentTurns}")
        if self.coldOffloadGraceSeconds < 0:
            errors.append(f"coldOffloadGraceSeconds must be >= 0, got {self.coldOffloadGraceSeconds}")
        if self.summaryMaxTokens <= 0:
            errors.append(f"summaryMaxTokens must be > 0, got {self.summaryMaxTokens}")
        if self.batchSummaryMaxTokens <= 0:
            errors.append(
                f"batchSummaryMaxTokens must be > 0, got {self.batchSummaryMaxTokens}"
            )

        # 落盘参数
        if self.persistCharThreshold <= 0:
            errors.append(
                f"persistCharThreshold must be > 0, got {self.persistCharThreshold}"
            )
        if self.persistPreviewChars < 0:
            errors.append(
                f"persistPreviewChars must be >= 0, got {self.persistPreviewChars}"
            )
        if self.storeMaxTotalSize <= 0:
            errors.append(
                f"storeMaxTotalSize must be > 0, got {self.storeMaxTotalSize}"
            )

        return errors

    # ---- 序列化 ----

    @staticmethod
    def FromDict(data: dict) -> AgentConfig:
        """从字典反序列化配置。

        支持三种格式：
        1. 扁平格式：所有字段位于顶层。
        2. 嵌套格式（loop/context/persist）：向后兼容旧配置。
        3. 混合格式：部分嵌套 + 部分扁平。
        """
        # 嵌套格式：从子字典中提取字段
        loopData = data.get("loop", {}) if isinstance(data.get("loop"), dict) else data
        contextData = data.get("context", {}) if isinstance(data.get("context"), dict) else data
        persistData = data.get("persist", {}) if isinstance(data.get("persist"), dict) else data

        # 优先级：嵌套子字典 > 顶层扁平 > 默认值
        return AgentConfig(
            # 循环行为
            maxTurns=loopData.get("maxTurns", data.get("maxTurns", 25)),
            tokenBudget=loopData.get("tokenBudget", data.get("tokenBudget", 0)),
            runTimeout=loopData.get("runTimeout", data.get("runTimeout", 0.0)),
            # 路径配置
            workspaceRoot=loopData.get("workspaceRoot", data.get("workspaceRoot", str(ERoad.WORKSPACE))),
            skillsDir=loopData.get("skillsDir", data.get("skillsDir", str(ERoad.SKILLS_DIR))),
            rulesDir=loopData.get("rulesDir", data.get("rulesDir", str(ERoad.RULES_DIR))),
            mcpJsonPath=loopData.get("mcpJsonPath", data.get("mcpJsonPath", str(ERoad.MCP_JSON_PATH))),
            memoryDir=loopData.get("memoryDir", data.get("memoryDir", str(ERoad.MEMORY_DIR))),
            # Token 预算
            maxTokens=contextData.get("maxTokens", data.get("maxTokens", 128000)),
            reserveTokens=contextData.get("reserveTokens", data.get("reserveTokens", 4096)),
            # 压缩参数
            compactThreshold=contextData.get("compactThreshold", data.get("compactThreshold", 0.85)),
            keepRecentTurns=contextData.get("keepRecentTurns", data.get("keepRecentTurns", 5)),
            coldOffloadGraceSeconds=contextData.get(
                "coldOffloadGraceSeconds", data.get("coldOffloadGraceSeconds", 300)
            ),
            autoColdOffload=contextData.get("autoColdOffload", data.get("autoColdOffload", True)),
            summaryMaxTokens=contextData.get("summaryMaxTokens", data.get("summaryMaxTokens", 512)),
            batchSummaryMaxTokens=contextData.get(
                "batchSummaryMaxTokens", data.get("batchSummaryMaxTokens", 2048)
            ),
            compactionPrompt=contextData.get("compactionPrompt", data.get("compactionPrompt")),
            # 落盘参数
            enablePersist=persistData.get("enablePersist", data.get("enablePersist", True)),
            persistCharThreshold=persistData.get(
                "persistCharThreshold", data.get("persistCharThreshold", 25000)
            ),
            persistPreviewChars=persistData.get(
                "persistPreviewChars", data.get("persistPreviewChars", 5000)
            ),
            storeDir=persistData.get("storeDir", data.get("storeDir", str(ERoad.STORE_PATH))),
            storeMaxTotalSize=persistData.get(
                "storeMaxTotalSize", data.get("storeMaxTotalSize", 500 * 1024 * 1024)
            ),
            storeMaxFileCount=persistData.get(
                "storeMaxFileCount", data.get("storeMaxFileCount", 100)
            ),
            # 子系统开关
            enableWorkflow=data.get("enableWorkflow", False),
            # 外部密钥
            tavilyApiKey=data.get("tavilyApiKey", ""),
        )

    def ToDict(self) -> dict:
        """序列化为扁平字典。"""
        return {f.name: getattr(self, f.name) for f in fields(self)}

    @classmethod
    def Default(cls) -> AgentConfig:
        """返回默认配置的浅拷贝，每次调用返回独立实例，防止全局污染。"""
        return copy.copy(cls.DEFAULT)


AgentConfig.DEFAULT = AgentConfig()
