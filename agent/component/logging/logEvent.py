"""结构化日志事件 —— Agent 运行时各类可观测事件的标准化数据模型。

每条 LogEvent 携带时间戳、事件类型、会话标识、轮次索引、耗时和元数据，
可序列化为 JSON 供下游分析，也可格式化为人类可读文本。
"""

from __future__ import annotations

import time
from typing import Any

from .eLogEventType import ELogEventType


class LogEvent:
    """Agent 运行时结构化事件。

    Attributes:
        timestamp: 事件发生时间（time.monotonic()，单调递增，适合计算耗时）。
        wallTime: 事件发生墙钟时间（time.time()，适合日志对齐）。
        eventType: 事件类型枚举。
        sessionId: 所属会话 ID（前 8 位）。
        turnIndex: 所属推理轮次（-1 表示非轮次事件）。
        duration: 事件耗时秒数（-1.0 表示不适用）。
        metadata: 事件特定元数据（键值对，不同 eventType 有不同 schema）。
    """

    __slots__ = ("timestamp", "wallTime", "eventType", "sessionId", "turnIndex", "duration", "metadata")

    def __init__(
        self,
        eventType: ELogEventType,
        sessionId: str = "",
        turnIndex: int = -1,
        duration: float = -1.0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.timestamp: float = time.monotonic()
        self.wallTime: float = time.time()
        self.eventType: ELogEventType = eventType
        self.sessionId: str = sessionId
        self.turnIndex: int = turnIndex
        self.duration: float = duration
        self.metadata: dict[str, Any] = metadata or {}

    # ---- 序列化 ----

    def ToDict(self) -> dict[str, Any]:
        """转换为字典（JSON 序列化用）。"""
        import datetime

        wallIso = datetime.datetime.fromtimestamp(self.wallTime).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
        return {
            "ts": wallIso,
            "type": self.eventType.name,
            "session": self.sessionId,
            "turn": self.turnIndex,
            "duration": round(self.duration, 3) if self.duration >= 0 else None,
            **self.metadata,
        }

    def ToJsonLine(self) -> str:
        """转换为 JSON Lines 格式（一行一条，便于流式写入和 jq 分析）。"""
        import json

        return json.dumps(self.ToDict(), ensure_ascii=False, default=str)

    def ToTextLine(self) -> str:
        """转换为人类可读的文本行。"""
        import datetime

        wallStr = datetime.datetime.fromtimestamp(self.wallTime).strftime("%H:%M:%S")
        turnStr = f"T{self.turnIndex}" if self.turnIndex >= 0 else "  -"
        durStr = f"{self.duration:.2f}s" if self.duration >= 0 else "    -"
        metaStr = " ".join(f"{k}={v}" for k, v in self.metadata.items() if v is not None)
        return f"[{wallStr}] [{self.eventType.name:20s}] {turnStr} {durStr:>8s} {metaStr}"

    def __repr__(self) -> str:
        return f"LogEvent({self.eventType.name}, turn={self.turnIndex}, dur={self.duration:.3f}s)"
