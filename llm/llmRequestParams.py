"""LLM 请求参数数据对象，封装 Provider 级别的额外调用参数。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .provider.chatMessage import ChatMessage, ChatResponse, ToolSpec


@dataclass
class LLMRequestParams:
    """LLM 调用请求参数

    Attributes:
        temperature: 采样温度，范围 [0, 2]，默认 0.7。
        maxTokens: 最大生成 token 数，0 表示不限制。
        enableThinking: 启用 Extended Thinking（Anthropic Claude）。
        thinkingBudget: Extended Thinking 预算 token 数。
        enableCache: 启用 KV-Cache / Prompt Caching（Anthropic）。
        extraParams: 透传到 API 的额外参数（top_p、frequency_penalty 等）。
        tools: 请求级工具列表，None 表示不携带工具。
        onBeforeRequest: 请求前回调，传入归一化后的消息列表。
        onAfterRequest: 请求后回调，传入完整响应。
        onError: 请求异常回调，传入异常对象。
    """

    temperature: float = 0.7
    maxTokens: int = 0
    enableThinking: bool = False
    thinkingBudget: int = 0
    enableCache: bool = True
    extraParams: Optional[dict[str, Any]] = None

    # ——— 请求级回调 ———
    onBeforeRequest: Optional[Callable[[list[ChatMessage]], None]] = None
    onAfterRequest: Optional[Callable[[ChatResponse], None]] = None
    onError: Optional[Callable[[Exception], None]] = None

    # ——— 请求级工具 ———
    tools: Optional[list[ToolSpec]] = None


# 静态默认实例，外部只读使用，避免重复分配
LLMRequestParams.DEFAULT = LLMRequestParams()
