"""Channel 配置 —— 控制 Agent 创建参数与群组并发策略。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from agent import AgentConfig


@dataclass
class ChannelConfig:
    """Channel 创建配置。

    Attributes:
        modelName: LLM 模型名称，None 时使用 Settings.defaultModel。
        agentConfig: Agent 运行时配置，None 时使用 Settings.AgentConfig()。
        enableWorkflow: 是否启用工作流子系统。
        maxConcurrentGroups: 最大并发群组数，0 表示无限制。
        commandPrefix: 指令触发前缀字符，消息内容以此开头时走指令分发而非 Agent。
    """

    modelName: Optional[str] = None
    agentConfig: Optional[AgentConfig] = None
    enableWorkflow: bool = True
    maxConcurrentGroups: int = 0
    commandPrefix: str = "/"
