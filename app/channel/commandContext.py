"""CommandContext —— 指令处理上下文，提供群组 Agent 组件访问与响应输出。

CommandContext 是 Channel 指令系统的核心上下文：
- 持有当前群组的 GroupContext，提供 Agent / Session / LLM 等组件便捷访问。
- 提供 Print / PrintDim 等输出方法，默认累积到内部缓冲区，
  指令执行完毕后由 BaseChannel 统一投递。
- 子类可 override 输出方法实现平台特定行为
  （如 CLI 直接写终端，飞书通过 API 回复消息）。

与 CLI 的 CliContext 对标，CliContext 可继承此类并 override 输出方法。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List

from agent import (
    Agent,
    DataComponent,
    HarnessComponent,
    LLMComponent,
    SessionComponent,
    ToolComponent,
)
from agent.component.contex.contextComponent import ContextComponent

if TYPE_CHECKING:
    from .baseChannel import BaseChannel
    from .channelMessage import ChannelMessage
    from .commandRegistry import CommandRegistry
    from .groupContext import GroupContext


class CommandContext:
    """指令处理上下文 —— 群组 Agent 组件访问 + 响应输出。

    由 BaseChannel.CreateCommandContext 创建，传入当前群组上下文和原始消息。
    命令 handler 通过此上下文访问 Agent 组件、输出响应、请求退出等。

    Attributes:
        GroupId: 群组唯一标识。
        UserId: 发送者唯一标识。
        UserName: 发送者显示名称。
    """

    def __init__(
        self,
        channel: BaseChannel,
        groupContext: GroupContext,
        message: ChannelMessage,
        registry: CommandRegistry,
    ) -> None:
        self._channel: BaseChannel = channel
        self._groupContext: GroupContext = groupContext
        self._message: ChannelMessage = message
        self._registry: CommandRegistry = registry
        self._wantsExit: bool = False
        self._responseBuffer: List[str] = []

    # ---- 群组 / 消息信息 ----

    @property
    def GroupId(self) -> str:
        return self._groupContext.groupId

    @property
    def UserId(self) -> str:
        return self._message.userId

    @property
    def UserName(self) -> str:
        return self._message.userName

    @property
    def Channel(self) -> BaseChannel:
        return self._channel

    @property
    def Registry(self) -> CommandRegistry:
        return self._registry

    # ---- 组件访问 ----

    @property
    def Agent(self) -> Agent:
        return self._groupContext.agent

    @property
    def Session(self) -> SessionComponent:
        return self._groupContext.agent.GetComponent(SessionComponent)

    @property
    def LLM(self) -> LLMComponent:
        return self._groupContext.agent.GetComponent(LLMComponent)

    @property
    def Context(self) -> ContextComponent:
        return self._groupContext.agent.GetComponent(ContextComponent)

    @property
    def Tools(self) -> ToolComponent:
        return self._groupContext.agent.GetComponent(ToolComponent)

    @property
    def Data(self) -> DataComponent:
        return self._groupContext.agent.GetComponent(DataComponent)

    @property
    def Harness(self) -> HarnessComponent:
        return self._groupContext.agent.GetComponent(HarnessComponent)

    # ---- 退出控制 ----

    @property
    def WantsExit(self) -> bool:
        """是否已请求退出。"""
        return self._wantsExit

    def RequestExit(self) -> None:
        """请求退出 Channel（由平台决定具体行为）。"""
        self._wantsExit = True

    # ---- 输出 ----

    def Print(self, text: str) -> None:
        """追加一行到响应缓冲区。子类可 override 实现即时输出。"""
        self._responseBuffer.append(text)

    def PrintDim(self, text: str) -> None:
        """追加一行 dim 文本到响应缓冲区。"""
        self._responseBuffer.append(text)

    def PrintWarning(self, text: str) -> None:
        """追加一行警告到响应缓冲区。"""
        self._responseBuffer.append(text)

    def PrintError(self, text: str) -> None:
        """追加一行错误到响应缓冲区。"""
        self._responseBuffer.append(text)

    def GetResponseText(self) -> str:
        """获取累积的响应文本（合并缓冲区各行）。"""
        return "\n".join(self._responseBuffer)

    @property
    def HasResponse(self) -> bool:
        """是否有累积的响应文本。"""
        return len(self._responseBuffer) > 0

    # ---- 格式化工具 ----

    @staticmethod
    def FormatK(value: int) -> str:
        """将 token 数格式化为 k 单位。"""
        return f"{value / 1000.0:.1f}k"
