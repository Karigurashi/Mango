"""会话缓冲区 —— 消息的唯一归属地，Memory 与 AI 对话之间的内存工作区。

Session 存储本次会话的全部 ContextMessage，包含原始消息和压缩摘要。
ContextEngine 不存储任何消息，只负责从 Session 读取、组织、回写。
"""

from __future__ import annotations

import time
import uuid

from common.const import ERole

from .contextMessage import ContextMessage
from agent.memory import Memory


class Session:
    """Agent 运行时的消息存储器。

    Session 是"账本"——完整记录所有消息（含压缩摘要），每条有唯一 messageId。
    ContextEngine 是"调度器"——从 Session 读取，决定发给 LLM 什么，压缩后回写 Session。

    Attributes:
        sessionId: 会话唯一标识（UUID）。
        messages: ContextMessage 列表。
        memory: 关联的持久化 Memory 实例（可选）。
        createdAt: 创建时间戳。
        updatedAt: 最后更新时间戳。
    """

    def __init__(self, sessionId: str | None = None) -> None:
        self.sessionId = sessionId or str(uuid.uuid4())
        self.messages: list[ContextMessage] = []
        self.memory: Memory | None = None
        self.createdAt = time.time()
        self.updatedAt = self.createdAt
        self._compressedSummary: ContextMessage | None = None
        self._compressedUpToTurnIndex: int = -1
        self._forkBaselineCount: int = 0

    # ---- Memory 读写 ----

    def LoadFromMemory(self, memory: Memory) -> None:
        """关联 Memory 实例。

        持久化块由 ContextAssembler.BuildAsync 通过 memory.LoadContextBlocks() 注入。

        Args:
            memory: 已初始化的 Memory 实例。
        """
        self.memory = memory

    def SaveToMemory(self) -> None:
        """将本次会话摘要持久化到 Memory。"""
        if self.memory is None:
            return

        summary = self._ExtractSessionSummary()
        if summary:
            self.memory.SaveSessionSummary(self.sessionId, summary)

    def _ExtractSessionSummary(self) -> str:
        """提取可用于跨会话恢复的会话摘要。"""
        if self._compressedSummary is not None:
            return self._compressedSummary.content

        for msg in reversed(self.messages):
            if msg.role == ERole.ASSISTANT and msg.content.strip():
                return msg.content[:2000]
        return ""

    # ---- 消息管理 ----

    def Append(self, msg: ContextMessage) -> None:
        """追加一条 ContextMessage。

        Args:
            msg: ContextMessage 实例（messageId 为空时自动生成）。
        """
        if not msg.messageId:
            msg.messageId = str(uuid.uuid4())
        self.messages.append(msg)
        self.updatedAt = time.time()

    def AppendBatch(self, msgs: list[ContextMessage]) -> None:
        """批量追加消息。"""
        for msg in msgs:
            if not msg.messageId:
                msg.messageId = str(uuid.uuid4())
        self.messages.extend(msgs)
        self.updatedAt = time.time()

    def GetAll(self) -> list[ContextMessage]:
        """返回所有消息的浅拷贝。"""
        return list(self.messages)

    def GetLastN(self, n: int) -> list[ContextMessage]:
        """返回最后 N 条消息。"""
        return self.messages[-n:] if n < len(self.messages) else list(self.messages)

    def GetMessageCount(self) -> int:
        """返回消息总数。"""
        return len(self.messages)

    def FindById(self, messageId: str) -> ContextMessage | None:
        """按 messageId 查找消息。

        Args:
            messageId: 消息唯一标识。

        Returns:
            找到的 ContextMessage，不存在时返回 None。
        """
        for msg in self.messages:
            if msg.messageId == messageId:
                return msg
        return None

    def MarkCompacted(self, messageId: str) -> bool:
        """将指定消息标记为已压缩（后续组装时跳过）。

        Args:
            messageId: 消息唯一标识。

        Returns:
            是否成功标记。
        """
        msg = self.FindById(messageId)
        if msg is None:
            return False
        msg.isCompacted = True
        self.updatedAt = time.time()
        return True

    def Clear(self) -> None:
        """清空所有消息（慎用）。"""
        self.messages.clear()
        self.ClearCompressedSummary()
        self.updatedAt = time.time()

    # ---- 压缩摘要（独立存储，不在 messages 队列中） ----

    @property
    def CompressedSummary(self) -> ContextMessage | None:
        """唯一的压缩摘要，None 表示尚无压缩。"""
        return self._compressedSummary

    @property
    def CompressedUpToTurnIndex(self) -> int:
        """压缩覆盖到的最大 turnIndex，-1 表示无压缩。"""
        return self._compressedUpToTurnIndex

    def SetCompressedSummary(self, summary: ContextMessage, upToTurnIndex: int) -> None:
        """设置唯一的压缩摘要及其覆盖范围。

        Args:
            summary: 压缩生成的摘要消息。
            upToTurnIndex: 本次压缩覆盖到哪个 turnIndex。
        """
        self._compressedSummary = summary
        self._compressedUpToTurnIndex = upToTurnIndex
        self.updatedAt = time.time()

    def ClearCompressedSummary(self) -> None:
        """清除压缩摘要。"""
        self._compressedSummary = None
        self._compressedUpToTurnIndex = -1
        self.updatedAt = time.time()

    # ---- 魔法方法 ----

    def __repr__(self) -> str:
        compressed = f", compressedUpToTurn={self._compressedUpToTurnIndex}" if self._compressedSummary else ""
        return (
            f"Session(id={self.sessionId[:8]}..., "
            f"messages={len(self.messages)}, "
            f"hasMemory={self.memory is not None}{compressed})"
        )

    def __len__(self) -> int:
        return len(self.messages)
