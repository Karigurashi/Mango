"""DataComponent —— Agent 运行时数据组件，持有 AgentConfig 作为配置成员。

DataComponent 是 IComponent，通过 OnInitialize/OnDestroy 感知生命周期，
统一管理 Agent 运行时的配置数据、状态机和 LLM 实例。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import copy

from agent.core.baseComponent import IComponent
from common.logger import Logger
from .agentConfig import AgentConfig
from .eAgentState import EAgentState, VALID_TRANSITIONS

if TYPE_CHECKING:
    from agent.core.baseAgent import BaseAgent
    from llm.baseLLM import BaseLLM


class DataComponent(IComponent):
    """Agent 运行时数据组件，持有 AgentConfig 配置。

    Attributes:
        config: Agent 运行时配置（循环行为、Token 预算、上下文引擎、重试策略等）。
        state: Agent 当前运行状态（通过 setter 校验合法转移）。
        llm: 底层 BaseLLM 实例。
        agentId: Agent 自增标识，每次实例化自动递增。
    """

    _nextAgentId: int = 0

    def __init__(self) -> None:
        DataComponent._nextAgentId += 1
        self._agentId: int = DataComponent._nextAgentId
        self._config: AgentConfig = copy.copy(AgentConfig.DEFAULT)
        self._llm: BaseLLM | None = None
        self._state: EAgentState = EAgentState.IDLE

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

    @property
    def state(self) -> EAgentState:
        """Agent 当前运行状态。"""
        return self._state

    @state.setter
    def state(self, newState: EAgentState) -> None:
        """设置新状态，非法转移仅警告不阻断（避免破坏现有流程，便于排查）。"""
        if newState != self._state:
            allowedTargets = VALID_TRANSITIONS.get(self._state, set())
            if newState not in allowedTargets:
                Logger.Warning(
                    f"Invalid state transition: {self._state.name} -> {newState.name}"
                )
        self._state = newState

    @property
    def agentId(self) -> int:
        """Agent 自增标识，只读。"""
        return self._agentId

    # ---- 生命周期 ----

    def OnInitialize(self, agent: BaseAgent) -> None:
        """挂载后回调。"""
        pass

    def OnDestroy(self) -> None:
        """从 BaseAgent 卸载时回调。"""
        pass

    # ---- 魔法方法 ----

    def __repr__(self) -> str:
        return (
            f"DataComponent(maxTurns={self._config.maxTurns}, "
            f"tokenBudget={self._config.tokenBudget})"
        )
