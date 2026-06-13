"""DataComponent —— Agent 运行时数据组件，持有 AgentConfig 作为配置成员。

DataComponent 是 IComponent，通过 OnInitialize/OnDestroy 感知生命周期，
统一管理 Agent 运行时的配置数据。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent.core.baseComponent import IComponent
from .agentConfig import AgentConfig
from .eAgentState import EAgentState

if TYPE_CHECKING:
    from agent.core.baseAgent import BaseAgent
    from llm.baseLLM import BaseLLM


class DataComponent(IComponent):
    """Agent 运行时数据组件，持有 AgentConfig 配置。

    Attributes:
        config: Agent 运行时配置（循环行为、Token 预算、上下文引擎、重试策略等）。
        state: Agent 当前运行状态。
        llm: 底层 BaseLLM 实例。
    """

    def __init__(self) -> None:
        self._config: AgentConfig = AgentConfig.Default()
        self._llm: BaseLLM | None = None
        self.state = EAgentState.IDLE

    # ---- 属性 ----

    @property
    def config(self) -> AgentConfig:
        """Agent 运行时配置。"""
        return self._config

    @config.setter
    def config(self, value: AgentConfig) -> None:
        self._config = value

    @property
    def llm(self) -> BaseLLM:
        """底层 BaseLLM 实例，未设置时抛出 RuntimeError。"""
        if self._llm is None:
            raise RuntimeError("DataComponent.llm has not been set. Assign a BaseLLM instance before use.")
        return self._llm

    @llm.setter
    def llm(self, value: BaseLLM) -> None:
        self._llm = value

    # ---- 生命周期 ----

    def OnInitialize(self, agent: BaseAgent) -> None:
        """挂载后初始化。"""
        pass

    def OnDestroy(self) -> None:
        """从 BaseAgent 卸载时回调。"""
        pass

    # ---- 魔法方法 ----

    def __repr__(self) -> str:
        return (
            f"DataComponent(maxTurns={self._config.maxTurns}, "
            f"tokenBudget={self._config.tokenBudget}, "
            f"autoCompact={self._config.autoCompact}, "
            f"maxRetries={self._config.maxRetries})"
        )
