"""Memory 抽象接口 —— 跨会话持久化记忆的统一入口。

Working Memory 由 Session 承载；本模块负责 Episodic / Semantic 等跨 Session 内容。
当前为第一期 stub：NullMemory（空实现）+ FileMemory（文件后端）。
"""

from __future__ import annotations

import json
import os
import time
from abc import ABC, abstractmethod


class Memory(ABC):
    """Agent 持久化记忆抽象基类。

    ContextAssembler 通过 LoadContextBlocks() 读取并注入 LOD0；
    Session.SaveToMemory() 通过 SaveSessionSummary() 写回会话摘要。
    """

    @abstractmethod
    def LoadContextBlocks(self) -> list[str]:
        """加载需注入 Context 的持久化文本块（用户偏好、上次会话摘要等）。"""

    @abstractmethod
    def SaveSessionSummary(self, sessionId: str, summary: str) -> None:
        """持久化本次会话摘要。"""

    def SaveContextBlocks(self, blocks: list[str]) -> None:
        """持久化 Context 注入块（可选覆盖，默认 no-op）。"""


class NullMemory(Memory):
    """空实现 —— 不读写任何持久化内容。"""

    def LoadContextBlocks(self) -> list[str]:
        return []

    def SaveSessionSummary(self, sessionId: str, summary: str) -> None:
        pass


class FileMemory(Memory):
    """文件后端 —— 将会话摘要和 Context 块存为 JSON 文件。

    目录结构::

        {storageDir}/
            context_blocks.json   # LoadContextBlocks 来源
            sessions/{sessionId}.json
    """

    def __init__(self, storageDir: str = ".agent/memory") -> None:
        self._storageDir = storageDir
        os.makedirs(storageDir, exist_ok=True)

    @property
    def StorageDir(self) -> str:
        return self._storageDir

    def LoadContextBlocks(self) -> list[str]:
        path = os.path.join(self._storageDir, "context_blocks.json")
        if not os.path.isfile(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            blocks = data.get("blocks", [])
            return [b for b in blocks if isinstance(b, str) and b.strip()]
        except (OSError, json.JSONDecodeError):
            return []

    def SaveContextBlocks(self, blocks: list[str]) -> None:
        path = os.path.join(self._storageDir, "context_blocks.json")
        payload = {"blocks": blocks, "updatedAt": time.time()}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def SaveSessionSummary(self, sessionId: str, summary: str) -> None:
        if not summary.strip():
            return
        sessionsDir = os.path.join(self._storageDir, "sessions")
        os.makedirs(sessionsDir, exist_ok=True)
        path = os.path.join(sessionsDir, f"{sessionId}.json")
        payload = {
            "sessionId": sessionId,
            "summary": summary,
            "updatedAt": time.time(),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def LoadSessionSummary(self, sessionId: str) -> str | None:
        """读取指定会话的摘要（供后续 Memory 扩展使用）。"""
        path = os.path.join(self._storageDir, "sessions", f"{sessionId}.json")
        if not os.path.isfile(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("summary")
        except (OSError, json.JSONDecodeError):
            return None

    def __repr__(self) -> str:
        return f"FileMemory(dir={self._storageDir!r})"
