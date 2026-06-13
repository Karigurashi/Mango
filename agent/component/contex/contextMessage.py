"""上下文消息 —— Session 中存储的标准消息类型，带唯一 ID 和 LOD 标记。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from common.const import ERole
from llm.provider.chatMessage import ChatMessage

from .eContextLodLevel import EContextLodLevel


@dataclass(slots=True)
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
    """

    _chatMessage: ChatMessage
    lodLevel: EContextLodLevel
    turnIndex: int = 0
    messageId: str = field(default_factory=lambda: str(uuid.uuid4()))
    summarizedFrom: list[str] = field(default_factory=list)
    isCompacted: bool = False
    isAgedOut: bool = False
    _agedOutByteSize: int = field(default=0, init=False, repr=False, compare=False)
    _tokenEstimate: int | None = field(default=None, init=False, repr=False, compare=False)

    def __init__(
        self,
        chatMessage: ChatMessage,
        lodLevel: EContextLodLevel,
        turnIndex: int = 0,
        messageId: str | None = None,
        summarizedFrom: list[str] | None = None,
        isCompacted: bool = False,
        isAgedOut: bool = False,
    ) -> None:
        self._chatMessage = chatMessage
        self.messageId = messageId or str(uuid.uuid4())
        self.lodLevel = lodLevel
        self.turnIndex = turnIndex
        self.summarizedFrom = summarizedFrom or []
        self.isCompacted = isCompacted
        self.isAgedOut = isAgedOut
        # token 估算缓存，内容变更时由 content setter 置空，避免每轮重复编码
        self._tokenEstimate = None
        self._agedOutByteSize = 0

    # ---- role / content 属性（代理到 ChatMessage）----

    @property
    def role(self) -> ERole:
        return self._chatMessage.role

    @role.setter
    def role(self, value: ERole) -> None:
        self._chatMessage.role = value
        self._chatMessage.InvalidateCache()

    @property
    def content(self) -> str:
        return self._chatMessage.content

    @content.setter
    def content(self, value: str) -> None:
        self._chatMessage.content = value
        self._chatMessage.InvalidateCache()
        self._tokenEstimate = None

    # ---- token 估算缓存 ----

    def GetTokenEstimate(self) -> int | None:
        """返回缓存的 token 估值，未缓存时返回 None。"""
        return self._tokenEstimate

    def SetTokenEstimate(self, value: int) -> None:
        """写入 token 估值缓存。"""
        self._tokenEstimate = value

    def MarkAgedOut(self, byteSize: int) -> None:
        """将消息标记为已冷卸载，不修改原始内容。

        与 isCompacted 同构：标记在数据模型，投影在组装层（ContextLodManager.AssembleMessages）。
        """
        self.isAgedOut = True
        self._agedOutByteSize = byteSize
        self._tokenEstimate = None

    @property
    def AgedOutByteSize(self) -> int:
        """已冷卸载消息的原始内容字节数，供投影层构建占位文本。"""
        return self._agedOutByteSize

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
    ) -> ContextMessage:
        """静态工厂：创建 ContextMessage，lodLevel 由调用方显式传入。

        LOD 分类职责在 ContextComponent，不在此工厂内自动判定。

        Returns:
            构造好的 ContextMessage。
        """
        return ContextMessage(
            chatMessage=chatMessage,
            lodLevel=lodLevel,
            turnIndex=turnIndex,
            messageId=messageId,
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
            isAgedOut=self.isAgedOut,
        )

    # ---- 冷卸载投影（供组装层使用，不修改原始数据） ----

    def CreateAgedOutProjection(self) -> ContextMessage:
        """创建冷卸载投影消息：保留元数据（messageId/turnIndex/lodLevel/toolCallId），
        content 替换为占位文本。原始消息不被修改。

        供 ContextLodManager.AssembleMessages 在组装时调用，
        实现数据模型与展示逻辑的分离：标记在数据，投影在组装。
        """
        byteSize = self._agedOutByteSize
        placeholder = (
            f"[Content aged out of hot tail: "
            f"{byteSize / 1024:.1f}KB. Re-run the tool if needed.]"
        )
        import copy

        projectedChat = ChatMessage(
            role=self._chatMessage.role,
            content=placeholder,
            toolCalls=copy.deepcopy(self._chatMessage.toolCalls) if self._chatMessage.toolCalls else None,
            toolCallId=self._chatMessage.toolCallId,
            cacheControl=self._chatMessage.cacheControl,
        )
        return ContextMessage(
            chatMessage=projectedChat,
            lodLevel=self.lodLevel,
            turnIndex=self.turnIndex,
            messageId=self.messageId,
            summarizedFrom=list(self.summarizedFrom),
            isCompacted=self.isCompacted,
            isAgedOut=False,  # 投影本身不再 aged
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
