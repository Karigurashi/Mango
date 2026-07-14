"""CommandContext —— 指令处理上下文，提供服务化 API 与响应输出。

CommandContext 是 Channel 指令系统的核心上下文：
- 通过服务方法封装 Agent 组件操作，不暴露 Agent / Component 类型。
- 提供 Print / PrintDim 等输出方法，默认累积到内部缓冲区，
  指令执行完毕后由 BaseChannel 统一投递。
- 子类可 override 输出方法实现平台特定行为
  （如 CLI 直接写终端，飞书通过 API 回复消息）。

Agent 完全封装：外部无法通过 CommandContext 获取 Agent 实例或其组件，
所有操作通过 NewSession / GetModelName / SwitchModel 等服务方法完成。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from agent import AgentConfig
    from ...baseChannel import BaseChannel
    from ...channelMessage import ChannelMessage
    from ..group import GroupContext
    from .commandRegistry import CommandRegistry


class CommandContext:
    """指令处理上下文 —— 服务化 API + 响应输出。

    由 BaseChannel.CreateCommandContext 创建，传入当前群组上下文和原始消息。
    命令 handler 通过此上下文调用服务方法、输出响应、请求退出等。

    Agent 组件不对外暴露，所有操作通过服务方法完成。

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

    # ---- Session 服务 ----

    def NewSession(self) -> int:
        """创建新会话，清空对话历史，返回新会话 ID。"""
        from agent import SessionComponent
        return self._groupContext._agent.GetComponent(SessionComponent).NewSession()

    def GetActiveSessionId(self) -> int:
        """获取当前活跃会话 ID。"""
        from agent import SessionComponent
        return self._groupContext._agent.GetComponent(SessionComponent).ActiveSessionId

    def GetSessionIds(self) -> list[int]:
        """获取所有会话 ID 列表。"""
        from agent import SessionComponent
        return self._groupContext._agent.GetComponent(SessionComponent).GetSessionIds()

    def GetSessionMessageCount(self, sessionId: int) -> int:
        """获取指定会话的消息数。

        Args:
            sessionId: 会话 ID。

        Returns:
            消息数，会话不存在时返回 0。
        """
        from agent import SessionComponent
        session = self._groupContext._agent.GetComponent(SessionComponent).GetSession(sessionId)
        return session.GetMessageCount() if session else 0

    def SaveSessionToMarkdown(self) -> int:
        """将当前会话以 Markdown 格式保存到文件，返回保存的消息数。"""
        from agent import SessionComponent
        return self._groupContext._agent.GetComponent(SessionComponent).SaveToMarkdown()

    # ---- LLM 服务 ----

    def GetModelName(self) -> str:
        """获取当前模型名称。"""
        from agent import LLMComponent
        return self._groupContext._agent.GetComponent(LLMComponent).modelName

    def GetProviderName(self) -> str:
        """获取当前 LLM Provider 名称。"""
        from agent import LLMComponent
        return self._groupContext._agent.GetComponent(LLMComponent).providerName

    def SwitchModel(self, modelName: str) -> bool:
        """切换到指定模型。

        内部同时更新 DataComponent 和 LLMComponent。

        Args:
            modelName: 目标模型名称。

        Returns:
            是否切换成功。
        """
        from llm import LLMManager
        from agent import DataComponent, LLMComponent

        try:
            newLlm = LLMManager.GetProvider(modelName)
        except KeyError:
            return False

        agent = self._groupContext._agent
        agent.GetComponent(DataComponent).llm = newLlm
        agent.GetComponent(LLMComponent).llm = newLlm
        return True

    def GetTotalPromptTokens(self) -> int:
        """获取累计输入 Token 数。"""
        from agent import LLMComponent
        return self._groupContext._agent.GetComponent(LLMComponent).TotalPromptTokens

    def GetTotalCompletionTokens(self) -> int:
        """获取累计输出 Token 数。"""
        from agent import LLMComponent
        return self._groupContext._agent.GetComponent(LLMComponent).TotalCompletionTokens

    def GetLastPromptTokens(self) -> int:
        """获取最近一次输入 Token 数。"""
        from agent import LLMComponent
        return self._groupContext._agent.GetComponent(LLMComponent).LastPromptTokens

    def GetLastCompletionTokens(self) -> int:
        """获取最近一次输出 Token 数。"""
        from agent import LLMComponent
        return self._groupContext._agent.GetComponent(LLMComponent).LastCompletionTokens

    def GetLastCacheHitRate(self) -> float:
        """获取最近一次缓存命中率。"""
        from agent import LLMComponent
        return self._groupContext._agent.GetComponent(LLMComponent).LastCacheHitRate

    # ---- Context 服务 ----

    async def CompactContextAsync(self, force: bool = False) -> int:
        """触发上下文压缩。

        Args:
            force: 是否强制压缩。

        Returns:
            释放的 Token 数。
        """
        from agent.component.contex.contextComponent import ContextComponent
        return await self._groupContext._agent.GetComponent(ContextComponent).CompactAsync(force=force)

    # ---- Tool 服务 ----

    def GetToolCount(self) -> int:
        """获取已注册工具数量。"""
        from agent import ToolComponent
        return self._groupContext._agent.GetComponent(ToolComponent).Count()

    def GetAllTools(self) -> list[dict]:
        """获取所有已注册工具信息。

        Returns:
            工具信息列表，每项含 name / category / description 字段。
        """
        from agent import ToolComponent
        tools = self._groupContext._agent.GetComponent(ToolComponent).GetAll()
        return [
            {"name": name, "category": tool.category.name, "description": tool.description}
            for name, tool in tools.items()
        ]

    # ---- Data 服务 ----

    def GetAgentState(self) -> str:
        """获取 Agent 当前状态名称。"""
        from agent import DataComponent
        return self._groupContext._agent.GetComponent(DataComponent).state.name

    def GetAgentConfig(self) -> AgentConfig:
        """获取 Agent 运行时配置（纯 dataclass，无 Agent 引用）。"""
        from agent import DataComponent
        return self._groupContext._agent.GetComponent(DataComponent).config

    # ---- Harness 服务 ----

    async def RebuildHarnessAsync(self) -> int:
        """重建 harness（重载 rules / skills / MCP 工具）。

        Returns:
            重建后注册的工具数量。
        """
        from agent import HarnessComponent, ToolComponent
        agent = self._groupContext._agent
        await agent.GetComponent(HarnessComponent).BuildAsync(force=True)
        return agent.GetComponent(ToolComponent).Count()

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
