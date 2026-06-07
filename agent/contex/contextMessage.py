"""上下文消息 —— Session 中存储的标准消息类型，带唯一 ID 和 LOD 标记。"""

from __future__ import annotations

import uuid

from common.const import ERole
from llm.provider.chatMessage import ChatMessage

from .eContextLodLevel import EContextLodLevel


class ContextMessage:
    """Session 中存储的单条消息。

    role/content 直接复用 ChatMessage，不再单独存储，避免 ToModelMessages 时重复创建对象。

    Attributes:
        messageId: 唯一标识（UUID）。
        chatMessage: 关联的 ChatMessage 实例（role/content 的来源）。
        lodLevel: LOD 等级。
        turnIndex: 所属回合序号。
        summarizedFrom: 若为摘要消息，记录被摘要的源消息 ID 列表。
        isCompacted: 原始消息是否已被压缩（压缩后跳过注入）。
        metadata: 扩展元数据（isThinking、isDecision 等）。
    """

    def __init__(
        self,
        chatMessage: ChatMessage,
        lodLevel: EContextLodLevel,
        turnIndex: int = 0,
        messageId: str | None = None,
        summarizedFrom: list[str] | None = None,
        isCompacted: bool = False,
        metadata: dict | None = None,
    ) -> None:
        self._chatMessage = chatMessage
        self.messageId = messageId or str(uuid.uuid4())
        self.lodLevel = lodLevel
        self.turnIndex = turnIndex
        self.summarizedFrom = summarizedFrom or []
        self.isCompacted = isCompacted
        self.metadata = metadata or {}

    # ---- role / content 属性（代理到 ChatMessage）----

    @property
    def role(self) -> ERole:
        return self._chatMessage.role

    @role.setter
    def role(self, value: ERole) -> None:
        self._chatMessage.role = value

    @property
    def content(self) -> str:
        return self._chatMessage.content

    @content.setter
    def content(self, value: str) -> None:
        self._chatMessage.content = value

    @property
    def chatMessage(self) -> ChatMessage:
        """返回关联的 ChatMessage 引用，可直接传入 LLM 调用。"""
        return self._chatMessage

    # ---- 静态工厂 ----

    @staticmethod
    def Create(
        chatMessage: ChatMessage,
        lodLevel: EContextLodLevel,
        turnIndex: int = 0,
        messageId: str | None = None,
        metadata: dict | None = None,
    ) -> ContextMessage:
        """静态工厂：创建 ContextMessage，lodLevel 由调用方显式传入。

        LOD 分类职责在 ContextEngine，不在此工厂内自动判定。

        Returns:
            构造好的 ContextMessage。
        """
        return ContextMessage(
            chatMessage=chatMessage,
            lodLevel=lodLevel,
            turnIndex=turnIndex,
            messageId=messageId,
            metadata=metadata,
        )

    # ---- 复制 ----

    def Clone(self, *, newMessageId: bool = True) -> "ContextMessage":
        """深拷贝消息，供 Subagent fork / merge 使用。"""
        import copy

        cm = self._chatMessage
        clonedChat = ChatMessage(
            role=cm.role,
            content=cm.content,
            toolCalls=copy.deepcopy(cm.toolCalls) if cm.toolCalls else None,
            toolCallId=cm.toolCallId,
            cacheControl=cm.cacheControl,
        )
        return ContextMessage(
            chatMessage=clonedChat,
            lodLevel=self.lodLevel,
            turnIndex=self.turnIndex,
            messageId=str(uuid.uuid4()) if newMessageId else self.messageId,
            summarizedFrom=list(self.summarizedFrom),
            isCompacted=self.isCompacted,
            metadata=dict(self.metadata),
        )

    # ---- 转换 ----

    def ToDict(self) -> dict:
        """转换为模型 API 格式的字典（调试/序列化用）。"""
        return {"role": self.role, "content": self.content}

    def __repr__(self) -> str:
        compactedHint = ", compacted" if self.isCompacted else ""
        summaryHint = f", summarizes={self.summarizedFrom}" if self.summarizedFrom else ""
        return (
            f"ContextMessage(id={self.messageId[:8]}..., "
            f"role={self.role!r}, "
            f"lod={self.lodLevel.name}, "
            f"turn={self.turnIndex}"
            f"{compactedHint}{summaryHint})"
        )
