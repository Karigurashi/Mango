"""飞书通道配置 —— 封装飞书机器人的应用凭证与运行参数。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class FeishuConfig:
    """飞书机器人通道配置。

    Attributes:
        appId: 飞书应用 App ID。
        appSecret: 飞书应用 App Secret。
        modelName: LLM 模型名称，None 时使用 Settings.defaultModel。
        commandPrefix: 指令触发前缀字符，消息内容以此开头时走指令分发而非 Agent。
    """

    appId: str = ""
    appSecret: str = ""
    modelName: Optional[str] = None
    commandPrefix: str = "/"
