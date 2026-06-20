"""LLM 配置对象，与 models.json 文件结构一一对应。

LLMConfig — 根类型，映射整个 JSON 文件（models 列表 + defaultModel）。
LLMModel  — 子类型，映射单个模型条目。
"""

from __future__ import annotations

from typing import Any


class LLMConfig:
    """models.json 文件的根类型。

    由 CommonUtil.JsonLoadFromFile 直接反序列化，models 列表中的每个 dict
    自动转换为 LLMModel 实例。

    Attributes:
        models: 模型配置列表。
        defaultModel: 默认模型名。
        timeout: 请求超时秒数（所有模型共享，透传给 SDK 与框架层 asyncio.wait_for）。
        maxRetries: 框架层 LLM 重试最大次数（所有模型共享）。
        retryBaseDelay: 重试基础等待秒数。
        retryMaxDelay: 重试最大等待秒数。
    """

    def __init__(
        self,
        models: list[dict | LLMModel],
        defaultModel: str = "",
        timeout: float = 120.0,
        maxRetries: int = 3,
        retryBaseDelay: float = 1.0,
        retryMaxDelay: float = 30.0,
        **kwargs: Any,
    ) -> None:
        self.models = [
            LLMModel(**m) if isinstance(m, dict) else m for m in models
        ]
        self.defaultModel = defaultModel
        self.timeout = timeout
        self.maxRetries = maxRetries
        self.retryBaseDelay = retryBaseDelay
        self.retryMaxDelay = retryMaxDelay

    def __repr__(self) -> str:
        return (f"LLMConfig(models={len(self.models)}, defaultModel={self.defaultModel!r}, "
                f"maxRetries={self.maxRetries})")


class LLMModel:
    """单一 LLM 的连接与运行时配置。

    LLMModel 可直接由 CommonUtil.JsonDeserialize 从 JSON 反序列化，
    多余字段会被忽略。

    重试策略由 LLMConfig 全局统一管理，不在单模型级别配置。

    Attributes:
        name: 配置别名，用于在调度器中按名称查找。
        url: 模型 API 端点地址（base URL）。
        apiKey: 认证密钥。
        provider: 厂商标识（openai / anthropic / gemini）。
        modelName: 实际模型名，缺省时沿用 name。
        thinkingBudget: Anthropic Extended Thinking 预算 token 数。
    """

    def __init__(
        self,
        name: str,
        url: str,
        apiKey: str,
        provider: str = "",
        modelName: str = "",
        thinkingBudget: int = 4000,
        **kwargs: Any,
    ) -> None:
        self.name = name
        self.url = url
        self.apiKey = apiKey
        self.provider = provider
        self.modelName = modelName or name
        self.thinkingBudget = thinkingBudget

    def __repr__(self) -> str:
        return f"LLMModel(name={self.name!r}, modelName={self.modelName!r}, url={self.url!r})"

    def ToDict(self) -> dict:
        return {
            "name": self.name,
            "url": self.url,
            "apiKey": self.apiKey,
            "provider": self.provider,
            "modelName": self.modelName,
            "thinkingBudget": self.thinkingBudget,
        }

