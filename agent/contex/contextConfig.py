"""上下文配置 —— JSON 可配化的上下文引擎参数。"""

from __future__ import annotations


class ContextConfig:
    """上下文引擎的所有可配置参数。

    可通过 JSON 反序列化或直接构造，驱动 ContextLodManager 和 ContextEngine 的行为。

    Attributes:
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
        storeDir: 内容外存目录（默认 ".contex/store"）。
        storeMaxAge: 外存文件最大保留时间，单位秒（默认 86400，24h）。
        autoCompact: 是否启用自动压缩（默认 True）。
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

    def __init__(
        self,
        maxTokens: int = 128000,
        reserveTokens: int = 4096,
        compactThreshold: float = 0.85,
        recentTurnCount: int = 5,
        lod3LineThreshold: int = 500,
        lod3SizeThreshold: int = 102400,
        keepRecentTurns: int = 5,
        summaryMaxTokens: int = 512,
        batchSummaryMaxTokens: int = 2048,
        compactionPrompt: str | None = None,
        storeDir: str = ".contex/store",
        storeMaxAge: int = 86400,
        autoCompact: bool = True,
    ) -> None:
        self.maxTokens = maxTokens
        self.reserveTokens = reserveTokens
        self.compactThreshold = compactThreshold
        self.recentTurnCount = recentTurnCount
        self.lod3LineThreshold = lod3LineThreshold
        self.lod3SizeThreshold = lod3SizeThreshold
        self.keepRecentTurns = keepRecentTurns
        self.summaryMaxTokens = summaryMaxTokens
        self.batchSummaryMaxTokens = batchSummaryMaxTokens
        self.compactionPrompt = compactionPrompt
        self.storeDir = storeDir
        self.storeMaxAge = storeMaxAge
        self.autoCompact = autoCompact

    @property
    def effectiveBudget(self) -> int:
        """实际可用于上下文组装的 token 预算。"""
        return self.maxTokens - self.reserveTokens

    @staticmethod
    def FromDict(data: dict) -> "ContextConfig":
        """从字典反序列化配置。"""
        return ContextConfig(
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
            storeDir=data.get("storeDir", ".contex/store"),
            storeMaxAge=data.get("storeMaxAge", 86400),
            autoCompact=data.get("autoCompact", True),
        )

    def ToDict(self) -> dict:
        """序列化为字典。"""
        return {
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
            "storeDir": self.storeDir,
            "storeMaxAge": self.storeMaxAge,
            "autoCompact": self.autoCompact,
        }

    def __repr__(self) -> str:
        return (
            f"ContextConfig(maxTokens={self.maxTokens}, "
            f"reserveTokens={self.reserveTokens}, "
            f"compactThreshold={self.compactThreshold}, "
            f"autoCompact={self.autoCompact})"
        )
