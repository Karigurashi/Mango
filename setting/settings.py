"""全局设置静态类 —— 模块导入时自动加载 settings.json。

settings.json 按模块切分为 model / agent / channel 三节，
Settings 类负责统一解析并对外暴露类型化访问器。

使用方式::

    from setting import Settings

    # 模型层
    models = Settings.Models()
    timeout = Settings.Timeout()

    # Agent 层
    config = Settings.AgentConfig()

    # Channel 层
    channelConfig = Settings.ChannelConfig()
"""

from __future__ import annotations

import copy
from pathlib import Path

from common import SerializeUtil
from common.const import ERoad
from llm.llmConfig import LLMConfig, LLMModel
from agent.component.data.agentConfig import AgentConfig
from app.channel.channelConfig import ChannelConfig


class Settings:
    """全局设置静态类，模块导入时自动加载 settings.json。

    支持通过 InitFromPath 手动切换配置路径或热加载。

    模块划分：
    - model：LLM 模型列表 + 全局 LLM 参数（超时、重试）
    - agent：Agent 运行时配置（Token 预算、压缩、落盘等）
    - channel：Channel 平台适配配置（并发、指令前缀等）
    """

    SETTINGS_PATH: str = str(ERoad.SETTINGS_JSON)

    _llmConfig: LLMConfig = LLMConfig()
    _agentConfig: AgentConfig = AgentConfig()
    _channelConfig: ChannelConfig = ChannelConfig()

    # ==================== 加载 ====================

    @classmethod
    def InitFromPath(cls, jsonPath: str) -> None:
        """手动切换配置路径，立即重新加载。

        可多次调用以热切换配置，每次调用会清空已有数据。

        Args:
            jsonPath: settings.json 格式的配置文件路径。

        Raises:
            FileNotFoundError: 配置文件不存在。
        """
        cls._LoadFromPath(jsonPath)

    @classmethod
    def _LoadFromPath(cls, jsonPath: str) -> None:
        """从指定 JSON 路径加载全部模块配置。"""
        if not Path(jsonPath).exists():
            raise FileNotFoundError(f"Settings file not found: {jsonPath}")

        content = Path(jsonPath).read_text(encoding="utf-8")
        data = SerializeUtil.FromJson(content)

        # ---- model 模块 ----
        cls._llmConfig = SerializeUtil.FromDict(data.get("model", {}), LLMConfig)

        # ---- agent 模块 ----
        cls._agentConfig = SerializeUtil.FromDict(data.get("agent", {}), AgentConfig)

        # ---- channel 模块 ----
        cls._channelConfig = SerializeUtil.FromDict(data.get("channel", {}), ChannelConfig)

    # ==================== model 模块 ====================

    @classmethod
    def Models(cls) -> list[LLMModel]:
        """获取所有模型配置列表。"""
        return cls._llmConfig.models

    @classmethod
    def GetModel(cls, name: str) -> LLMModel:
        """按名称查找模型配置。

        Raises:
            KeyError: 模型不存在。
        """
        for model in cls._llmConfig.models:
            if model.name == name:
                return model
        raise KeyError(
            f"Model '{name}' not found. Available: {cls.ListModelNames()}"
        )

    @classmethod
    def ListModelNames(cls) -> list[str]:
        """获取所有已注册模型的名称列表。"""
        return [m.name for m in cls._llmConfig.models]

    @classmethod
    def DefaultModel(cls) -> str:
        """获取默认模型名。"""
        if not cls._llmConfig.defaultModel and cls._llmConfig.models:
            return cls._llmConfig.models[0].name
        return cls._llmConfig.defaultModel

    @classmethod
    def Timeout(cls) -> float:
        """请求超时秒数。"""
        return cls._llmConfig.timeout

    @classmethod
    def MaxRetries(cls) -> int:
        """框架层 LLM 重试最大次数。"""
        return cls._llmConfig.maxRetries

    @classmethod
    def RetryBaseDelay(cls) -> float:
        """重试基础等待秒数。"""
        return cls._llmConfig.retryBaseDelay

    @classmethod
    def RetryMaxDelay(cls) -> float:
        """重试最大等待秒数。"""
        return cls._llmConfig.retryMaxDelay

    # ==================== agent 模块 ====================

    @classmethod
    def AgentConfig(cls) -> AgentConfig:
        """获取默认 Agent 运行时配置。

        每次调用返回浅拷贝，调用方可安全修改。

        Returns:
            AgentConfig 实例。
        """
        return copy.copy(cls._agentConfig)

    # ==================== channel 模块 ====================

    @classmethod
    def ChannelConfig(cls) -> ChannelConfig:
        """获取默认 Channel 配置。

        每次调用返回浅拷贝，调用方可安全修改。

        Returns:
            ChannelConfig 实例。
        """
        return copy.copy(cls._channelConfig)

    # ==================== 资源清理 ====================

    @classmethod
    def Reset(cls) -> None:
        """重置所有缓存，重新加载配置。"""
        cls._llmConfig = LLMConfig()
        cls._agentConfig = AgentConfig()
        cls._channelConfig = ChannelConfig()
        cls._LoadFromPath(cls.SETTINGS_PATH)


# 模块导入时自动加载默认配置
Settings._LoadFromPath(Settings.SETTINGS_PATH)
