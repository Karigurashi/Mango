"""飞书 API 客户端 —— 封装消息发送、表情反应等飞书开放平台 REST API。

使用 lark-oapi SDK 的异步方法（acreate / areply / adelete），
无需 asyncio.to_thread 包装，直接在事件循环中调用。
"""

from __future__ import annotations

import json
from typing import Optional

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    CreateMessageReactionRequest,
    CreateMessageReactionRequestBody,
    CreateMessageRequest,
    CreateMessageRequestBody,
    DeleteMessageReactionRequest,
    Emoji,
    PatchMessageRequest,
    PatchMessageRequestBody,
    ReplyMessageRequest,
    ReplyMessageRequestBody,
)

from common.cancellationToken import CancellationToken
from common.logger import Logger


class FeishuApi:
    """飞书开放平台 API 客户端。

    封装 lark-oapi SDK，直接使用 SDK 内置异步方法。
    所有 Async 方法均为协程，可在事件循环中直接 await。

    Attributes:
        _client: lark-oapi Client 实例。
    """

    def __init__(self, appId: str, appSecret: str) -> None:
        self._client: lark.Client = (
            lark.Client.builder()
            .app_id(appId)
            .app_secret(appSecret)
            .build()
        )

    # ---- 消息发送 ----

    async def SendTextAsync(
        self,
        chatId: str,
        text: str,
        cancellationToken: Optional[CancellationToken] = None,
    ) -> str:
        """发送文本消息到指定群聊。

        Args:
            chatId: 群聊 ID (chat_id)。
            text: 消息文本内容。
            cancellationToken: 取消令牌。

        Returns:
            消息 ID (message_id)，失败返回空字符串。
        """
        request = (
            CreateMessageRequest.builder()
            .receive_id_type("chat_id")
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(chatId)
                .msg_type("text")
                .content(json.dumps({"text": text}))
                .build()
            )
            .build()
        )
        response = await self._client.im.v1.message.acreate(request)
        if not response.success():
            Logger.Error(
                f"FeishuApi.SendText failed: code={response.code}, msg={response.msg}"
            )
            return ""
        return response.data.message_id

    async def SendCardAsync(
        self,
        chatId: str,
        cardJson: str,
        cancellationToken: Optional[CancellationToken] = None,
    ) -> str:
        """发送卡片消息到指定群聊。

        Args:
            chatId: 群聊 ID (chat_id)。
            cardJson: 飞书卡片 JSON 字符串 (msg_type=interactive)。
            cancellationToken: 取消令牌。

        Returns:
            消息 ID (message_id)，失败返回空字符串。
        """
        request = (
            CreateMessageRequest.builder()
            .receive_id_type("chat_id")
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(chatId)
                .msg_type("interactive")
                .content(cardJson)
                .build()
            )
            .build()
        )
        response = await self._client.im.v1.message.acreate(request)
        if not response.success():
            Logger.Error(
                f"FeishuApi.SendCard failed: code={response.code}, msg={response.msg}"
            )
            return ""
        return response.data.message_id

    async def UpdateCardAsync(
        self,
        messageId: str,
        cardJson: str,
        cancellationToken: Optional[CancellationToken] = None,
    ) -> bool:
        """PATCH 更新已发送卡片消息的内容。

        Args:
            messageId: 已发送卡片消息的 message_id。
            cardJson: 新的飞书卡片 JSON 字符串。
            cancellationToken: 取消令牌。

        Returns:
            是否更新成功。
        """
        request = (
            PatchMessageRequest.builder()
            .message_id(messageId)
            .request_body(
                PatchMessageRequestBody.builder()
                .content(cardJson)
                .build()
            )
            .build()
        )
        response = await self._client.im.v1.message.apatch(request)
        if not response.success():
            Logger.Error(
                f"FeishuApi.UpdateCard failed: code={response.code}, msg={response.msg}"
            )
            return False
        return True

    async def ReplyTextAsync(
        self,
        messageId: str,
        text: str,
        cancellationToken: Optional[CancellationToken] = None,
    ) -> str:
        """回复指定消息。

        Args:
            messageId: 被回复消息的 message_id。
            text: 回复文本内容。
            cancellationToken: 取消令牌。

        Returns:
            新消息 ID，失败返回空字符串。
        """
        request = (
            ReplyMessageRequest.builder()
            .message_id(messageId)
            .request_body(
                ReplyMessageRequestBody.builder()
                .msg_type("text")
                .content(json.dumps({"text": text}))
                .build()
            )
            .build()
        )
        response = await self._client.im.v1.message.areply(request)
        if not response.success():
            Logger.Error(
                f"FeishuApi.ReplyText failed: code={response.code}, msg={response.msg}"
            )
            return ""
        return response.data.message_id

    # ---- 表情反应 ----

    async def AddReactionAsync(
        self,
        messageId: str,
        emojiType: str,
        cancellationToken: Optional[CancellationToken] = None,
    ) -> str:
        """为消息添加表情反应。

        Args:
            messageId: 目标消息 ID。
            emojiType: 表情类型标识 (如 "SMILE", "THUMBSUP")。
            cancellationToken: 取消令牌。

        Returns:
            反应 ID (reaction_id)，失败返回空字符串。
        """
        request = (
            CreateMessageReactionRequest.builder()
            .message_id(messageId)
            .request_body(
                CreateMessageReactionRequestBody.builder()
                .reaction_type(Emoji.builder().emoji_type(emojiType).build())
                .build()
            )
            .build()
        )
        response = await self._client.im.v1.message_reaction.acreate(request)
        if not response.success():
            Logger.Error(
                f"FeishuApi.AddReaction failed: code={response.code}, msg={response.msg}"
            )
            return ""
        return response.data.reaction_id

    async def DeleteReactionAsync(
        self,
        messageId: str,
        reactionId: str,
        cancellationToken: Optional[CancellationToken] = None,
    ) -> bool:
        """删除消息的表情反应。

        Args:
            messageId: 目标消息 ID。
            reactionId: 反应 ID。
            cancellationToken: 取消令牌。

        Returns:
            是否删除成功。
        """
        request = (
            DeleteMessageReactionRequest.builder()
            .message_id(messageId)
            .reaction_id(reactionId)
            .build()
        )
        response = await self._client.im.v1.message_reaction.adelete(request)
        if not response.success():
            Logger.Error(
                f"FeishuApi.DeleteReaction failed: code={response.code}, msg={response.msg}"
            )
            return False
        return True
