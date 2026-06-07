"""LLM 配置对象，与 models.json 文件结构一一对应。

LLMConfig — 根类型，映射整个 JSON 文件（models 列表 + defaultModel）。
LLMModel  — 子类型，映射单个模型条目。
"""

from __future__ import annotations

from typing import Any

from .eTier import ETier


class LLMConfig:
    """models.json 文件的根类型。

    由 CommonUtil.JsonLoadFromFile 直接反序列化，models 列表中的每个 dict
    自动转换为 LLMModel 实例。

    Attributes:
        models: 模型配置列表。
        defaultModel: 默认模型名。
    """

    def __init__(
        self,
        models: list[dict | LLMModel],
        defaultModel: str = "",
        **kwargs: Any,
    ) -> None:
        self.models = [
            LLMModel(**m) if isinstance(m, dict) else m for m in models
        ]
        self.defaultModel = defaultModel

    def __repr__(self) -> str:
        return f"LLMConfig(models={len(self.models)}, defaultModel={self.defaultModel!r})"


class LLMModel:
    """单一 LLM 的连接与运行时配置。

    LLMModel 可直接由 CommonUtil.JsonDeserialize 从 JSON 反序列化，
    tier 自动完成 string ↔ ETier 转换，多余字段会被忽略。

    Attributes:
        name: 配置别名，用于在调度器中按名称查找。
        url: 模型 API 端点地址（base URL）。
        apiKey: 认证密钥。
        provider: 厂商标识（openai / anthropic / gemini）。
        modelName: 实际模型名，缺省时沿用 name。
        timeout: 请求超时秒数（透传给 SDK，框架层也用此值做 asyncio.wait_for 包装）。
        maxRetries: 最大重试次数（透传给 SDK）。
        streamTimeout: 流式请求总超时秒数（仅框架层 asyncio.wait_for，默认取 timeout * 2）。
        thinkingBudget: Anthropic Extended Thinking 预算 token 数。
        tier: 模型能力档位，用于按需调度。
    """

    _TIER_MAP: dict[str, ETier] = {"high": ETier.HIGH, "mid": ETier.MID, "low": ETier.LOW}

    def __init__(
        self,
        name: str,
        url: str,
        apiKey: str,
        provider: str = "",
        modelName: str = "",
        timeout: float = 120.0,
        maxRetries: int = 2,
        streamTimeout: float = 0.0,
        thinkingBudget: int = 4000,
        tier: ETier | str = ETier.MID,
        **kwargs: Any,
    ) -> None:
        self.name = name
        self.url = url
        self.apiKey = apiKey
        self.provider = provider
        self.modelName = modelName or name
        self.timeout = timeout
        self.maxRetries = maxRetries
        self.streamTimeout = streamTimeout if streamTimeout > 0 else timeout * 2
        self.thinkingBudget = thinkingBudget
        self.tier = self._NormalizeTier(tier)

    @classmethod
    def _NormalizeTier(cls, value: ETier | str) -> ETier:
        """将 tier 统一为 ETier 枚举。"""
        if isinstance(value, ETier):
            return value
        return cls._TIER_MAP.get(value, ETier.MID)

    def __repr__(self) -> str:
        return f"LLMModel(name={self.name!r}, modelName={self.modelName!r}, tier={self.tier.value}, url={self.url!r})"

    def ToDict(self) -> dict:
        return {
            "name": self.name,
            "url": self.url,
            "apiKey": self.apiKey,
            "provider": self.provider,
            "modelName": self.modelName,
            "timeout": self.timeout,
            "maxRetries": self.maxRetries,
            "streamTimeout": self.streamTimeout,
            "thinkingBudget": self.thinkingBudget,
            "tier": self.tier.value,
        }

