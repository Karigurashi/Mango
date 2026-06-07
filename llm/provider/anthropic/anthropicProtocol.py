"""Anthropic Messages API 协议层，封装消息格式、工具调用、KV-Cache、Extended Thinking。"""

from __future__ import annotations

from typing import Any

from common.const import ERole

from ..chatMessage import ChatMessage, ToolCall, ToolSpec


class AnthropicProtocol:
    """Anthropic Messages API 协议封装。

    负责 ChatMessage → Anthropic dict 转换、system 消息分离、
    ToolSpec → tools 数组、response content block → ToolCall 解析、
    KV-Cache (cache_control) 注入、Extended Thinking 配置。
    """

    # ---- 消息格式 ----

    @staticmethod
    def FormatMessages(
        messages: list[ChatMessage],
        enableCache: bool = False,
    ) -> tuple[list[str], list[dict]]:
        """分离 system 消息并转换格式。

        Returns:
            (systemPrompts, chatMessages): system 文本列表 + 对话消息列表。
        """
        systemPrompts: list[str] = []
        chatMessages: list[dict] = []
        for m in messages:
            if m.role == ERole.SYSTEM:
                systemPrompts.append(m.content)
            else:
                d = m.ToAnthropic()
                # KV-Cache 注入
                if enableCache and m.cacheControl:
                    d["cache_control"] = self.BuildCacheControl()
                chatMessages.append(d)
        return systemPrompts, chatMessages

    # ---- 工具格式 ----

    @staticmethod
    def FormatTools(tools: list[ToolSpec]) -> list[dict]:
        """将 ToolSpec 列表转为 Anthropic tools 数组。"""
        result: list[dict] = []
        for t in tools:
            result.append({
                "name": t.name,
                "description": t.description,
                "input_schema": t.parameters,
            })
        return result

    # ---- 工具调用解析 ----

    @staticmethod
    def ParseToolCalls(contentBlocks: list[Any]) -> list[ToolCall]:
        """从 Anthropic response content blocks 中提取 tool_use。"""
        result: list[ToolCall] = []
        for block in contentBlocks:
            if getattr(block, "type", "") == "tool_use":
                result.append(ToolCall(
                    id=getattr(block, "id", ""),
                    name=getattr(block, "name", ""),
                    arguments=getattr(block, "input", {}) or {},
                ))
        return result

    # ---- KV-Cache ----

    @staticmethod
    def BuildCacheControl() -> dict:
        """生成 Anthropic Prompt Caching 标记。"""
        return {"type": "ephemeral"}

    # ---- 参数构建 ----

    def BuildRequestParams(
        self,
        messages: list[ChatMessage],
        temperature: float,
        maxTokens: int,
        stream: bool,
        tools: list[ToolSpec] | None = None,
        enableThinking: bool = False,
        thinkingBudget: int = 0,
        enableCache: bool = False,
        **kwargs,
    ) -> dict:
        """聚合构建 Anthropic Messages API 请求参数。"""
        systemPrompts, chatMessages = self.FormatMessages(messages, enableCache)

        params: dict = {
            "model": kwargs.pop("_modelName", ""),
            "messages": chatMessages,
            "max_tokens": maxTokens if maxTokens > 0 else 4096,
            "temperature": temperature,
        }
        if systemPrompts:
            params["system"] = "\n".join(systemPrompts)
        if tools:
            params["tools"] = self.FormatTools(tools)

        # Extended Thinking
        if enableThinking and thinkingBudget > 0:
            params["thinking"] = {"type": "enabled", "budget_tokens": thinkingBudget}
            params["temperature"] = 1

        params.update(kwargs)
        return params
