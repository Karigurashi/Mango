"""大模型代理调度管理器。

从 JSON 配置自动创建对应 Provider（OpenAI / Anthropic / Gemini），
管理 Provider 连接池，按名称分发 BaseLLM。
"""

from __future__ import annotations

from pathlib import Path

from common.commonUtil import CommonUtil
from common.const import ERoad
from .baseLLM import BaseLLM
from .llmConfig import LLMConfig, LLMModel
from .provider.anthropic import AnthropicProvider
from .provider.gemini import GeminiProvider
from .provider.openai import OpenAIProvider


class LLMManager:
    """大模型调度管理器（静态类）。

    定死读取 workspace/models.json 配置，首次 GetProvider 时自动懒加载。
    同一模型只保有一个 Provider 连接，通过 GetProvider 分发 BaseLLM。

    使用方式::

        from llm import LLMManager

        # 按名称获取 Provider（首次调用自动加载配置）
        provider = LLMManager.GetProvider("gpt-4")
        response = provider.Invoke([ChatMessage.User("Hello")])
    """

    CONFIG_PATH = ERoad.MODELS_JSON

    _providers: dict[str, BaseLLM] = {}
    _config: LLMConfig | None = None
    _defaultModel: str = ""
    _loaded: bool = False

    # ==================== 懒加载 ====================

    @classmethod
    def _EnsureLoaded(cls) -> None:
        """首次访问时自动加载默认 models.json 配置。"""
        if cls._loaded:
            return
        cls._LoadFromPath(cls.CONFIG_PATH)

    @classmethod
    def _LoadFromPath(cls, jsonPath: str) -> None:
        """从指定 JSON 路径加载配置并初始化 Provider。

        会清空已有的 Provider，允许重新初始化。
        """
        if not Path(jsonPath).exists():
            raise FileNotFoundError(f"LLM config file not found: {jsonPath}")

        registry = CommonUtil.JsonLoadFromFile(jsonPath, LLMConfig)
        cls._config = registry
        cls._providers.clear()

        for model in registry.models:
            provider = cls._CreateProvider(model)
            cls._providers[model.name] = provider

        cls._defaultModel = registry.defaultModel
        if not cls._defaultModel and registry.models:
            cls._defaultModel = registry.models[0].name
        cls._loaded = True

    @classmethod
    def InitFromPath(cls, jsonPath: str) -> None:
        """手动初始化：传入 JSON 配置文件路径，直接解析并加载。

        可多次调用以切换配置，每次调用会清空已有的 Provider。

        Args:
            jsonPath: models.json 格式的配置文件路径。

        Raises:
            FileNotFoundError: 配置文件不存在。
        """
        cls._LoadFromPath(jsonPath)

    @classmethod
    def _CreateProvider(cls, config: LLMModel) -> BaseLLM:
        """根据 LLMModel 创建对应的 BaseLLM 实例。

        provider 优先取 config.provider，为空时根据 URL 自动推断。
        重试参数从全局 LLMConfig 读取，所有模型共享同一份配置。
        """
        providerType = config.provider or cls._InferProvider(config.url)
        retryKwargs = {
            "maxRetries": cls._config.maxRetries,
            "retryBaseDelay": cls._config.retryBaseDelay,
            "retryMaxDelay": cls._config.retryMaxDelay,
            "timeout": cls._config.timeout,
        }

        if providerType == "anthropic":
            return AnthropicProvider(config, **retryKwargs)
        elif providerType == "gemini":
            return GeminiProvider(config, **retryKwargs)
        else:
            return OpenAIProvider(config, **retryKwargs)

    @staticmethod
    def _InferProvider(url: str) -> str:
        """根据 URL 自动推断 provider 类型。"""
        urlLower = url.lower()
        if "anthropic" in urlLower:
            return "anthropic"
        if "gemini" in urlLower or "google" in urlLower:
            return "gemini"
        return "openai"

    @classmethod
    def _FindModel(cls, name: str) -> LLMModel:
        """从 config.models 列表中按名称查找模型。"""
        for model in cls._config.models:
            if model.name == name:
                return model
        raise KeyError(f"Model '{name}' not found. Available: {cls.ListModels()}")

    # ==================== Provider 获取 ====================

    @classmethod
    def GetProvider(cls, name: str | None = None) -> BaseLLM:
        """按模型名获取 BaseLLM Provider。

        首次调用时自动懒加载 models.json 配置。
        name 为空时自动回退到 LLMConfig 中的 defaultModel。

        Returns:
            BaseLLM 实例，可直接调用 Invoke / Stream / InvokeAsync / StreamAsync。
        """
        cls._EnsureLoaded()
        name = name or cls._defaultModel
        if name not in cls._providers:
            raise KeyError(f"Model '{name}' not found. Available: {cls.ListModels()}")
        return cls._providers[name]

    # ==================== 模型管理 ====================

    @classmethod
    def GetConfig(cls, name: str) -> LLMModel:
        cls._EnsureLoaded()
        return cls._FindModel(name)

    @classmethod
    def ListModels(cls) -> list[str]:
        cls._EnsureLoaded()
        return list(cls._providers.keys())

    @classmethod
    def AddModel(cls, model: LLMModel) -> None:
        cls._EnsureLoaded()
        cls._config.models.append(model)
        cls._providers[model.name] = cls._CreateProvider(model)

    @classmethod
    def RemoveModel(cls, name: str) -> None:
        cls._EnsureLoaded()
        model = cls._FindModel(name)
        cls._config.models.remove(model)
        cls._providers.pop(name, None)

    @classmethod
    def DefaultModel(cls) -> str:
        """获取默认模型名。"""
        cls._EnsureLoaded()
        return cls._defaultModel

    @classmethod
    def SetDefaultModel(cls, value: str) -> None:
        """设置默认模型名。"""
        cls._EnsureLoaded()
        if value and value not in cls._providers:
            raise KeyError(f"Cannot set default: model '{value}' not registered.")
        cls._defaultModel = value

    # ==================== 资源清理 ====================

    @classmethod
    def Close(cls) -> None:
        """关闭所有 Provider 的同步连接池。"""
        for p in cls._providers.values():
            if hasattr(p, "Close"):
                p.Close()

    @classmethod
    async def CloseAsync(cls) -> None:
        """关闭所有 Provider 的异步连接池。"""
        for p in cls._providers.values():
            if hasattr(p, "CloseAsync"):
                await p.CloseAsync()
