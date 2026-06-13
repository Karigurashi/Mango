"""Agent 配置 —— 统一集中配置，控制 ReAct 循环行为、Token 预算、上下文引擎、重试策略。"""

from __future__ import annotations

from dataclasses import dataclass, field
import copy

from common.const import ERoad


@dataclass
class AgentConfig:
    """Agent 运行时统一配置，所有字段提供合理默认值。

    所有字段均为不可变类型（int/float/bool/str/tuple/NoneType），
    因此 copy.copy() 浅拷贝等价于 copy.deepcopy()，但性能更优。

    Attributes:
        maxTurns: 单次 Run 最大推理轮次，防止无限循环。
        tokenBudget: ContextComponent 组装预算（0 则用 maxTokens - reserveTokens）。
        autoCompact: 回合后是否自动触发上下文压缩。
        workspaceRoot: 工作区根目录。
        skillsDir: Skill 扫描目录（``**/SKILL.md``）。
        rulesDir: Rule 扫描目录（``*.rule.md``）。
        mcpJsonPath: MCP 配置文件路径（``.mcp.json``）。
        maxRetries: LLM 调用最大重试次数（仅对可重试错误生效）。
        retryBaseDelay: 重试基础等待秒数，实际延迟 = baseDelay * 2^attempt。
        retryMaxDelay: 重试最大等待秒数，防止退避过大。
        retryableStatusCodes: 触发重试的 HTTP 状态码集合。

        maxTokens: Token 预算上限（默认 128000）。
        reserveTokens: 为模型回复预留的 token 数（默认 4096）。
        compactThreshold: 触发压缩的上下文占用率阈值（0.0-1.0，默认 0.85）。
        recentTurnCount: "最近 N 轮" 的 N 值，影响 LOD 判定（默认 5）。
        lod3LineThreshold: 触发 LOD 3 外存的行数阈值（默认 500）。
        lod3SizeThreshold: 触发 LOD 3 外存的字节数阈值（默认 102400）。
        keepRecentTurns: 压缩时保留的最近完整轮数（默认 5）。
        summaryMaxTokens: 单条消息摘要 LLM 最大输出 token（默认 512）。
        batchSummaryMaxTokens: 批量压缩摘要 LLM 最大输出 token（默认 2048）。
        compactionPrompt: LLM 压缩时的自定义 prompt（None 则用内置默认）。
        enablePersist: 是否启用大结果落盘+预览（默认 True）。
        persistCharThreshold: 触发落盘的字符数阈值（默认 50000）。
        persistPreviewChars: 预览截断字符数（默认 500）。
        storeDir: 内容外存目录（默认 ".contex/store"）。
        storeMaxAge: 外存文件最大保留时间，单位秒（默认 86400，24h）。
    """

    # ---- 内置默认压缩 Prompt ----

    DEFAULT_SINGLE_SUMMARY_PROMPT = (
        "Summarize the following agent message in 1-3 concise sentences. "
        "Preserve key decisions, factual findings, and open questions. "
        "Drop redundant reasoning and irrelevant details."
    )

    DEFAULT_BATCH_SUMMARY_PROMPT = (
        "Summarize the following conversation history. "
        "Preserve all key decisions, important facts, unresolved questions, "
        "and the overall task context. Be concise but complete."
    )

    # ---- Agent 循环行为 ----

    maxTurns: int = 25
    tokenBudget: int = 0
    autoCompact: bool = True
    workspaceRoot: str = str(ERoad.WORKSPACE)
    skillsDir: str = str(ERoad.SKILLS_DIR)
    rulesDir: str = str(ERoad.RULES_DIR)
    mcpJsonPath: str = str(ERoad.MCP_JSON_PATH)
    maxRetries: int = 3
    retryBaseDelay: float = 1.0
    retryMaxDelay: float = 30.0
    retryableStatusCodes: tuple = (429, 500, 502, 503, 504)

    # ---- 上下文引擎 ----

    maxTokens: int = 128000
    reserveTokens: int = 4096
    compactThreshold: float = 0.85
    recentTurnCount: int = 5
    lod3LineThreshold: int = 500
    lod3SizeThreshold: int = 102400
    keepRecentTurns: int = 5
    summaryMaxTokens: int = 512
    batchSummaryMaxTokens: int = 2048
    compactionPrompt: str | None = None
    enablePersist: bool = True
    persistCharThreshold: int = 50000
    persistPreviewChars: int = 500
    storeDir: str = ".contex/store"
    storeMaxAge: int = 86400
    storeMaxFileSize: int = 10 * 1024 * 1024  # 单文件最大字节数（超限截断）
    storeMaxTotalSize: int = 500 * 1024 * 1024  # 外存目录总容量上限（超限LRU淘汰）
    memoryDir: str = ""
    runTimeout: float = 0.0  # 单次 Run 最大执行秒数，0 表示不限

    # ---- 属性 ----

    @property
    def effectiveBudget(self) -> int:
        """实际可用于上下文组装的 token 预算。

        tokenBudget > 0 时直接使用，否则按 maxTokens - reserveTokens 计算。
        """
        if self.tokenBudget > 0:
            return self.tokenBudget
        return self.maxTokens - self.reserveTokens

    # ---- 序列化 ----

    @staticmethod
    def FromDict(data: dict) -> AgentConfig:
        """从字典反序列化配置。"""
        return AgentConfig(
            maxTurns=data.get("maxTurns", 25),
            tokenBudget=data.get("tokenBudget", 0),
            autoCompact=data.get("autoCompact", True),
            workspaceRoot=data.get("workspaceRoot", str(ERoad.WORKSPACE)),
            skillsDir=data.get("skillsDir", str(ERoad.SKILLS_DIR)),
            rulesDir=data.get("rulesDir", str(ERoad.RULES_DIR)),
            mcpJsonPath=data.get("mcpJsonPath", str(ERoad.MCP_JSON_PATH)),
            maxRetries=data.get("maxRetries", 3),
            retryBaseDelay=data.get("retryBaseDelay", 1.0),
            retryMaxDelay=data.get("retryMaxDelay", 30.0),
            retryableStatusCodes=tuple(data.get("retryableStatusCodes", (429, 500, 502, 503, 504))),
            maxTokens=data.get("maxTokens", 128000),
            reserveTokens=data.get("reserveTokens", 4096),
            compactThreshold=data.get("compactThreshold", 0.85),
            recentTurnCount=data.get("recentTurnCount", 5),
            lod3LineThreshold=data.get("lod3LineThreshold", 500),
            lod3SizeThreshold=data.get("lod3SizeThreshold", 102400),
            keepRecentTurns=data.get("keepRecentTurns", 5),
            summaryMaxTokens=data.get("summaryMaxTokens", 512),
            batchSummaryMaxTokens=data.get("batchSummaryMaxTokens", 2048),
            compactionPrompt=data.get("compactionPrompt"),
            enablePersist=data.get("enablePersist", True),
            persistCharThreshold=data.get("persistCharThreshold", 50000),
            persistPreviewChars=data.get("persistPreviewChars", 500),
            storeDir=data.get("storeDir", ".contex/store"),
            storeMaxAge=data.get("storeMaxAge", 86400),
            storeMaxFileSize=data.get("storeMaxFileSize", 10 * 1024 * 1024),
            storeMaxTotalSize=data.get("storeMaxTotalSize", 500 * 1024 * 1024),
            memoryDir=data.get("memoryDir", ""),
            runTimeout=data.get("runTimeout", 0.0),
        )

    def ToDict(self) -> dict:
        """序列化为字典。"""
        return {
            "maxTurns": self.maxTurns,
            "tokenBudget": self.tokenBudget,
            "autoCompact": self.autoCompact,
            "workspaceRoot": self.workspaceRoot,
            "skillsDir": self.skillsDir,
            "rulesDir": self.rulesDir,
            "mcpJsonPath": self.mcpJsonPath,
            "maxRetries": self.maxRetries,
            "retryBaseDelay": self.retryBaseDelay,
            "retryMaxDelay": self.retryMaxDelay,
            "retryableStatusCodes": list(self.retryableStatusCodes),
            "maxTokens": self.maxTokens,
            "reserveTokens": self.reserveTokens,
            "compactThreshold": self.compactThreshold,
            "recentTurnCount": self.recentTurnCount,
            "lod3LineThreshold": self.lod3LineThreshold,
            "lod3SizeThreshold": self.lod3SizeThreshold,
            "keepRecentTurns": self.keepRecentTurns,
            "summaryMaxTokens": self.summaryMaxTokens,
            "batchSummaryMaxTokens": self.batchSummaryMaxTokens,
            "compactionPrompt": self.compactionPrompt,
            "enablePersist": self.enablePersist,
            "persistCharThreshold": self.persistCharThreshold,
            "persistPreviewChars": self.persistPreviewChars,
            "storeDir": self.storeDir,
            "storeMaxAge": self.storeMaxAge,
            "storeMaxFileSize": self.storeMaxFileSize,
            "storeMaxTotalSize": self.storeMaxTotalSize,
            "memoryDir": self.memoryDir,
            "runTimeout": self.runTimeout,
        }

    def __repr__(self) -> str:
        return (
            f"AgentConfig(maxTurns={self.maxTurns}, "
            f"tokenBudget={self.tokenBudget}, "
            f"autoCompact={self.autoCompact}, "
            f"maxTokens={self.maxTokens}, "
            f"maxRetries={self.maxRetries})"
        )

    # ---- 默认配置工厂 ----

    _DEFAULT_TEMPLATE: AgentConfig = None  # type: ignore[assignment]  延迟到类定义完成后赋值

    @classmethod
    def Default(cls) -> AgentConfig:
        """返回默认配置的深拷贝，每次调用返回独立实例，防止全局污染。

        调用方可以安全地修改返回的实例而不会影响其他 Agent。
        """
        return copy.copy(cls._DEFAULT_TEMPLATE)  # 浅拷贝即可：所有字段均为不可变类型


AgentConfig._DEFAULT_TEMPLATE = AgentConfig()
