"""Session —— 会话数据对象，消息的唯一归属地。

Session 是纯数据容器，封装单次会话的全部消息、压缩状态和元数据。
由 SessionComponent 管理生命周期，支持一个 Agent 持有多个 Session。
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from agent.component.contex.contextMessage import ContextMessage
from agent.component.contex.eContextLodLevel import EContextLodLevel
from common.const import ERole

if TYPE_CHECKING:
    pass


class Session:
    """会话数据对象 —— 消息的唯一归属地，纯数据容器。

    Session 持有单次会话的全部消息，压缩后直接替换消息列表，不单独存储摘要。
    消息的摄入、组装、压缩由 ContextComponent 负责，Session 仅提供读写接口。

    Attributes:
        sessionId: 会话唯一标识（int）。
    """

    def __init__(self, sessionId: int | None = None) -> None:
        self.sessionId: int = sessionId if sessionId is not None else uuid.uuid4().int
        self._residentMessages: list[ContextMessage] = []       # RESIDENT 常驻消息（独立存储）
        self._conversationMessages: list[ContextMessage] = []   # 非 RESIDENT 对话消息
        self.lod3Count = 0   # LOD3 消息计数，为 0 时 ClearLod3 跳过扫描

    # ---- RESIDENT 管理 ----

    def ReplaceResidents(self, newResidents: list[ContextMessage]) -> None:
        """原子替换全部 RESIDENT 消息，保留对话消息不变。

        Args:
            newResidents: 新的 RESIDENT 消息列表。
        """
        self._residentMessages = list(newResidents)

    # ---- 消息管理 ----

    def Append(self, msg: ContextMessage) -> None:
        """追加一条 ContextMessage，按 LOD 级别路由到对应列表。"""
        if msg.lodLevel == EContextLodLevel.RESIDENT:
            self._residentMessages.append(msg)
        else:
            self._conversationMessages.append(msg)
        if msg.lodLevel == EContextLodLevel.EXTERNAL_ONLY:
            self.lod3Count += 1

    def AppendBatch(self, msgs: list[ContextMessage]) -> None:
        """批量追加消息。"""
        residents: list[ContextMessage] = []
        conv: list[ContextMessage] = []
        for msg in msgs:
            if msg.lodLevel == EContextLodLevel.EXTERNAL_ONLY:
                self.lod3Count += 1
            if msg.lodLevel == EContextLodLevel.RESIDENT:
                residents.append(msg)
            else:
                conv.append(msg)
        self._residentMessages.extend(residents)
        self._conversationMessages.extend(conv)

    @property
    def residentMessages(self) -> list[ContextMessage]:
        """RESIDENT 常驻消息列表（只读，调用方不可原地修改）。"""
        return self._residentMessages

    @property
    def conversationMessages(self) -> list[ContextMessage]:
        """非 RESIDENT 对话消息列表（只读，调用方不可原地修改）。"""
        return self._conversationMessages

    def GetMessageCount(self) -> int:
        """返回消息总数。"""
        return len(self._residentMessages) + len(self._conversationMessages)

    def Clear(self) -> None:
        """清空所有非 RESIDENT 消息（慎用）。

        RESIDENT 常驻内容不清除，保证 harness 初始填充的
        System 规则、技能前缀等跨会话复用，无需反复重建。
        """
        self._conversationMessages.clear()
        self.lod3Count = 0

    def ApplyCompactionResult(self, compactedMessages: list[ContextMessage]) -> None:
        """使用压缩产物替换消息列表，RESIDENT 不可触碰。

        先 Clear 保留所有 RESIDENT（不可压缩），再追加压缩产物中的
        非 RESIDENT 消息（摘要 + 幸存的可丢弃消息）。

        Args:
            compactedMessages: ContextCompactor 产出的完整消息列表（含 RESIDENT，会被过滤）。
        """
        self.Clear()
        for msg in compactedMessages:
            if msg.lodLevel != EContextLodLevel.RESIDENT:
                self.Append(msg)

    def FixOrphanedToolCalls(self) -> int:
        """修复对话消息中孤立的 tool_call 链，原地修改。返回被移除的消息数。

        剔除 ASSISTANT 中无对应 TOOL 响应的 tool_call，并删除变为空壳的
        ASSISTANT 消息（无 content 且 toolCalls 已全被清理）。

        单趟反向遍历：O(n) 时间，O(m) 空间（m = 唯一 tool_call_id 数）。
        toolCalls 列表通过两指针原地过滤，零中间分配。
        逆向删除避免索引偏移影响前序元素。
        """
        removed = 0
        validIds: set[str] = set()
        messages = self._conversationMessages

        i = len(messages) - 1
        while i >= 0:
            m = messages[i]

            if m.role == ERole.TOOL and m.chatMessage.toolCallId:
                validIds.add(m.chatMessage.toolCallId)
                i -= 1
                continue

            if m.role != ERole.ASSISTANT or not m.chatMessage.toolCalls:
                i -= 1
                continue

            # Two-pointer in-place filter of toolCalls
            calls = m.chatMessage.toolCalls
            write = 0
            for read in range(len(calls)):
                if calls[read].id in validIds:
                    calls[write] = calls[read]
                    write += 1

            if write == len(calls):
                i -= 1
                continue  # all valid, skip

            if write == 0:
                m.chatMessage.toolCalls = None
            else:
                del calls[write:]

            m.chatMessage.InvalidateCache()

            # Delete empty-shell ASSISTANT (no content, no remaining toolCalls)
            if not m.content.strip() and not m.chatMessage.toolCalls:
                del messages[i]
                removed += 1

            i -= 1

        return removed

    def ClearLod3(self) -> int:
        """清除所有 LOD3 (EXTERNAL_ONLY) 消息，并剥离关联的 tool_call。

        从后往前一趟遍历：LOD3 TOOL 消息同步剥离前一 assistant 的对应
        tool_call，空壳 assistant 级联删除。

        Returns:
            实际被移除的消息数量。
        """
        if self.lod3Count == 0:
            return 0

        removed = 0
        removedLod3 = 0
        for i in range(len(self._conversationMessages) - 1, -1, -1):
            msg = self._conversationMessages[i]
            if msg.lodLevel != EContextLodLevel.EXTERNAL_ONLY:
                continue

            # LOD3 TOOL：剥离前一个 assistant 的对应 tool_call
            cascade = False
            if msg.role == ERole.TOOL and i > 0:
                prev = self._conversationMessages[i - 1]
                if prev.role == ERole.ASSISTANT and prev.chatMessage.toolCalls:
                    tcId = msg.chatMessage.toolCallId
                    if tcId:
                        kept = [tc for tc in prev.chatMessage.toolCalls if tc.id != tcId]
                        if not kept:
                            if prev.chatMessage.content:
                                prev.chatMessage.toolCalls = None
                                prev.chatMessage.InvalidateCache()
                            else:
                                cascade = True
                        else:
                            prev.chatMessage.toolCalls = kept
                            prev.chatMessage.InvalidateCache()

            if cascade:
                del self._conversationMessages[i - 1:i + 1]
                removed += 2
                removedLod3 += 1
            else:
                del self._conversationMessages[i]
                removed += 1
                removedLod3 += 1

        self.lod3Count -= removedLod3
        return removed

    # ---- 序列化 ----

    def ToJsonDict(self) -> dict:
        """全量序列化为 JSON 兼容字典，支持完整 Session 持久化与还原。"""
        return {
            "sessionId": self.sessionId,
            "messages": [m.ToJsonDict() for m in self._residentMessages + self._conversationMessages],
        }

    @staticmethod
    def FromJsonDict(data: dict) -> "Session":
        """从 JSON 字典还原完整 Session。"""
        session = Session(sessionId=data["sessionId"])
        for mData in data.get("messages", []):
            msg = ContextMessage.FromJsonDict(mData)
            session.Append(msg)
        return session

    # ---- 统计 ----

    def GetStats(self) -> dict:
        """返回会话统计信息。

        Returns:
            包含 ``messageCount``、``totalBytes`` 的字典。
        """
        allMsgs = self._residentMessages + self._conversationMessages
        return {
            "messageCount": len(allMsgs),
            "totalBytes": sum(
                len(m.content.encode("utf-8")) for m in allMsgs if m.content
            ),
        }

    # ---- 魔法方法 ----

    def __repr__(self) -> str:
        allMsgs = self._residentMessages + self._conversationMessages
        summaryCount = sum(1 for m in allMsgs if m.isSummary)
        summary = f", summaries={summaryCount}" if summaryCount > 0 else ""
        return (
            f"Session(id={self.sessionId}, "
            f"messages={len(allMsgs)}{summary})"
        )

    def __len__(self) -> int:
        return len(self._residentMessages) + len(self._conversationMessages)
