"""BaseChannel —— 多群消息路由框架基类。

统一封装「1 App → N 群 → 1 Agent/群」模式。各平台适配器
（飞书、Discord、VSCode Chat 等）继承 BaseChannel 并实现平台 I/O 钩子即可
接入 Agent 体系，无需关心 Agent 创建、事件订阅、消息序列化等底层细节。

内置指令系统：消息内容以指定前缀字符开头时，走指令分发而非 Agent 执行。
子类通过 RegisterCommand 注册指令、override CreateCommandContext 提供平台上下文。

架构概览::

    ┌─────────────────────────────────────────────┐
    │                BaseChannel                   │
    │  CommandRegistry (前缀匹配 → 指令分发)        │
    │  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
    │  │ GroupCtx │  │ GroupCtx │  │ GroupCtx │  │
    │  │  Agent A │  │  Agent B │  │  Agent C │  │
    │  │ Session  │  │ Session  │  │ Session  │  │
    │  └──────────┘  └──────────┘  └──────────┘  │
    └─────────────────────────────────────────────┘
           ↑              ↑              ↑
        groupId=A      groupId=B      groupId=C

入站消息流:
  普通消息:  Platform → ChannelMessage → ReceiveMessageAsync
             → EnsureGroup(groupId) → GroupContext.SendMessageAsync
             → Agent.RunStreamAsync → EventBus 事件
             → GroupContext._OnAgentEvent → OnAgentEventSync
             → 平台自行处理（累积 / 流式转发 / 投递响应）

  指令消息:  Platform → ChannelMessage → ReceiveMessageAsync
             → content.startswith(prefix) → _DispatchCommandAsync
             → CommandRegistry.DispatchAsync → Command.handler(ctx, args)
             → ctx 响应缓冲区 → OnSendResponseAsync 投递
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING, Dict, List, Optional

from common.cancellationToken import CancellationToken
from common.logger import Logger

from .channelConfig import ChannelConfig
from .channelMessage import ChannelMessage
from .builtinCommands import RegisterBuiltinCommands
from .command import Command
from .commandContext import CommandContext

if TYPE_CHECKING:
    from agent import Agent, AgentConfig, AgentManager, AgentStreamEvent
from .commandRegistry import CommandRegistry
from .eChannelState import EChannelState
from .groupContext import GroupContext


class BaseChannel:
    """多群消息路由框架基类。

    管理多个 GroupContext，每个 GroupContext 持有一个独立的 Agent 实例。
    入站消息按 groupId 路由到对应 GroupContext，Agent 事件通过钩子回传平台。

    内置指令系统：消息内容以 commandPrefix 开头时走指令分发，不经过 Agent。
    子类通过 RegisterCommand 注册指令、override CreateCommandContext
    提供平台特定的上下文（如 CLI 的即时终端输出）。

    子类需实现:
        - OnAgentEventSync: 接收 Agent 事件并自行处理（累积 / 流式转发 / 投递）（必需）。
        - OnStartAsync / OnStopAsync: 平台启动 / 停止逻辑（可选）。
        - OnSendResponseAsync: 响应投递便捷方法，供 OnAgentEventSync 内部调用（可选）。
        - CreateAgent: 自定义 Agent 创建（可选）。
        - CreateCommandContext: 自定义指令上下文（可选）。

    Usage::

        class FeishuChannel(BaseChannel):
            async def OnSendResponseAsync(self, groupId, content, cancellationToken=None):
                await self._api.SendMessage(groupId, content)

            async def OnStartAsync(self, cancellationToken=None):
                await self._api.StartWebhook()

        channel = FeishuChannel(ChannelConfig(modelName="deepseek-chat"))
        await channel.StartAsync()

        # 当飞书 webhook 收到消息时
        msg = ChannelMessage(groupId="group_123", userId="user_456", content="你好")
        await channel.ReceiveMessageAsync(msg)
    """

    def __init__(self, config: Optional[ChannelConfig] = None) -> None:
        self._config: ChannelConfig = config or ChannelConfig()
        self._groups: Dict[str, GroupContext] = {}
        self._state: EChannelState = EChannelState.STOPPED
        self._commandRegistry: CommandRegistry = CommandRegistry(self._config.commandPrefix)
        RegisterBuiltinCommands(self._commandRegistry)

    # ---- 生命周期 ----

    def Start(self) -> None:
        """同步入口，启动 Channel 并阻塞直到退出。"""
        import asyncio
        try:
            asyncio.run(self.StartAsync())
        except KeyboardInterrupt:
            pass

    async def StartAsync(
        self,
        cancellationToken: Optional[CancellationToken] = None,
    ) -> None:
        """启动 BaseChannel，触发平台启动钩子。

        Args:
            cancellationToken: 取消令牌。
        """
        if self._state != EChannelState.STOPPED:
            Logger.Warning(f"BaseChannel.StartAsync: already in state {self._state.name}")
            return

        self._state = EChannelState.STARTING
        try:
            self._state = EChannelState.RUNNING
            await self.OnStartAsync(cancellationToken)
            Logger.Info(f"BaseChannel started: {type(self).__name__}")
        except Exception as exc:
            self._state = EChannelState.ERROR
            Logger.Error(f"BaseChannel.StartAsync failed: {exc}")
            raise

    async def StopAsync(
        self,
        cancellationToken: Optional[CancellationToken] = None,
    ) -> None:
        """停止 BaseChannel，销毁所有群组并触发平台停止钩子。

        Args:
            cancellationToken: 取消令牌。
        """
        if self._state == EChannelState.STOPPED:
            return

        self._state = EChannelState.STOPPING

        # 销毁所有群组
        for groupId in list(self._groups.keys()):
            group = self._groups.pop(groupId, None)
            if group is not None:
                group.Destroy()
                self.OnGroupRemoved(groupId)

        try:
            await self.OnStopAsync(cancellationToken)
        except Exception as exc:
            Logger.Error(f"BaseChannel.OnStopAsync failed: {exc}")

        self._state = EChannelState.STOPPED
        Logger.Info(f"BaseChannel stopped: {type(self).__name__}")

    # ---- 平台钩子（子类 override） ----

    async def OnStartAsync(
        self,
        cancellationToken: Optional[CancellationToken] = None,
    ) -> None:
        """平台启动钩子（如连接 Webhook、注册事件回调）。

        子类 override 此方法实现平台特定的启动逻辑。默认无操作。

        Args:
            cancellationToken: 取消令牌。
        """
        pass

    async def OnStopAsync(
        self,
        cancellationToken: Optional[CancellationToken] = None,
    ) -> None:
        """平台停止钩子（如断开连接、释放资源）。

        子类 override 此方法实现平台特定的停止逻辑。默认无操作。

        Args:
            cancellationToken: 取消令牌。
        """
        pass

    async def OnSendResponseAsync(
        self,
        groupId: str,
        content: str,
        cancellationToken: Optional[CancellationToken] = None,
    ) -> None:
        """将响应投递到平台（便捷方法，供子类在 OnAgentEventSync 中调用）。

        GroupContext 不自动调用此方法。子类在 OnAgentEventSync 中
        自行累积文本后，可在 DONE 事件时调用此方法投递完整响应。

        Args:
            groupId: 目标群组 ID。
            content: Agent 产出的完整文本响应。
            cancellationToken: 取消令牌。
        """
        Logger.Warning(
            f"BaseChannel.OnSendResponseAsync not implemented: "
            f"groupId={groupId}, content_len={len(content)}"
        )

    def OnAgentEventSync(
        self,
        groupId: str,
        event: AgentStreamEvent,
    ) -> None:
        """Agent 流式事件同步转发钩子（子类应 override）。

        Agent 每产出一个事件即调用此方法。子类在此方法中自行决定
        如何处理事件：累积 TEXT_DELTA 文本、实时流式转发、在 DONE
        时投递完整响应等。

        Args:
            groupId: 事件来源群组 ID。
            event: Agent 流式事件。
        """
        pass

    def OnGroupCreated(self, groupId: str, groupContext: GroupContext) -> None:
        """新群创建回调，子类可 override 进行平台注册。

        Args:
            groupId: 新创建的群组 ID。
            groupContext: 新创建的群组上下文。
        """
        pass

    def OnGroupRemoved(self, groupId: str) -> None:
        """群移除回调，子类可 override 进行平台清理。

        Args:
            groupId: 被移除的群组 ID。
        """
        pass

    # ---- 指令系统 ----

    @property
    def CommandRegistry(self) -> CommandRegistry:
        """指令注册表实例。"""
        return self._commandRegistry

    def RegisterCommand(self, command: Command) -> None:
        """注册一条指令到注册表。

        Args:
            command: Command 实例。
        """
        self._commandRegistry.Register(command)

    def CreateCommandContext(
        self,
        groupContext: GroupContext,
        message: ChannelMessage,
    ) -> CommandContext:
        """创建指令处理上下文（子类可 override 提供平台特定上下文）。

        默认返回 CommandContext 基类实例。子类可 override 此方法
        返回平台特定子类（如 CLI 的 CliContext，提供即时终端输出）。

        Args:
            groupContext: 当前群组上下文。
            message: 触发指令的原始消息。

        Returns:
            CommandContext 实例。
        """
        return CommandContext(self, groupContext, message, self._commandRegistry)

    async def _DispatchCommandAsync(
        self,
        groupContext: GroupContext,
        message: ChannelMessage,
        cancellationToken: Optional[CancellationToken] = None,
    ) -> None:
        """分发指令并投递响应。

        指令若请求退出（WantsExit），直接将 Channel 状态置为 STOPPING，
        由外部主循环检测并停止。

        Args:
            groupContext: 当前群组上下文。
            message: 含前缀的原始消息。
            cancellationToken: 取消令牌。
        """
        ctx = self.CreateCommandContext(groupContext, message)
        await self._commandRegistry.DispatchAsync(message.content, ctx)

        if ctx.HasResponse:
            await self.OnSendResponseAsync(
                groupContext.groupId,
                ctx.GetResponseText(),
                cancellationToken,
            )

        if ctx.WantsExit:
            self._state = EChannelState.STOPPING

    # ---- 群组管理 ----

    def EnsureGroup(
        self,
        groupId: str,
        groupName: str = "",
    ) -> GroupContext:
        """获取或创建群组上下文。

        若 groupId 已存在则返回已有 GroupContext，否则创建新的
        Agent 实例并注册。新群创建后触发 OnGroupCreated 回调。

        Args:
            groupId: 群唯一标识。
            groupName: 群显示名称。

        Returns:
            该群对应的 GroupContext 实例。
        """
        existing = self._groups.get(groupId)
        if existing is not None:
            return existing

        if (
            self._config.maxConcurrentGroups > 0
            and len(self._groups) >= self._config.maxConcurrentGroups
        ):
            raise RuntimeError(
                f"BaseChannel maxConcurrentGroups limit reached "
                f"({self._config.maxConcurrentGroups})"
            )

        agent = self.CreateAgent(groupId)
        group = GroupContext(self, groupId, groupName, agent)
        self._groups[groupId] = group
        self.OnGroupCreated(groupId, group)
        Logger.Info(
            f"BaseChannel: group created: groupId={groupId}, groupName={groupName}"
        )
        return group

    async def RemoveGroupAsync(
        self,
        groupId: str,
        cancellationToken: Optional[CancellationToken] = None,
    ) -> bool:
        """移除并销毁群组。

        先取消该群正在执行的 Agent 运行，等待其结束后销毁 Agent 实例，
        然后触发 OnGroupRemoved 回调。

        Args:
            groupId: 待移除的群 ID。
            cancellationToken: 取消令牌。

        Returns:
            是否成功移除（不存在时返回 False）。
        """
        group = self._groups.pop(groupId, None)
        if group is None:
            return False
        await group.DestroyAsync(cancellationToken)
        self.OnGroupRemoved(groupId)
        Logger.Info(f"BaseChannel: group removed: groupId={groupId}")
        return True

    def GetGroup(self, groupId: str) -> Optional[GroupContext]:
        """按 ID 获取群组上下文。

        Args:
            groupId: 群唯一标识。

        Returns:
            群组上下文实例，不存在时返回 None。
        """
        return self._groups.get(groupId)

    def GetGroupIds(self) -> List[str]:
        """返回所有群组 ID 列表。"""
        return list(self._groups.keys())

    @property
    def GroupCount(self) -> int:
        """当前群组总数。"""
        return len(self._groups)

    @property
    def State(self) -> EChannelState:
        """BaseChannel 当前运行状态。"""
        return self._state

    @property
    def ModelName(self) -> Optional[str]:
        """当前配置的模型名称。"""
        return self._config.modelName

    # ---- 消息路由 ----

    async def ReceiveMessageAsync(
        self,
        message: ChannelMessage,
        cancellationToken: Optional[CancellationToken] = None,
    ) -> None:
        """路由入站消息：前缀匹配则分发指令，否则路由到 Agent。

        消息内容以 commandPrefix 开头时走指令分发流程（_DispatchCommandAsync），
        否则投递给 GroupContext 进行 Agent 串行处理。不同群组的消息可通过
        asyncio.create_task 并发处理。

        Args:
            message: 标准化入站消息。
            cancellationToken: 取消令牌。
        """
        group = self.EnsureGroup(message.groupId, message.groupName)

        content = message.content
        if content and content.startswith(self._config.commandPrefix):
            await self._DispatchCommandAsync(group, message, cancellationToken)
        else:
            await group.SendMessageAsync(message, cancellationToken)

    # ---- Agent 工厂 ----

    def CreateAgent(self, groupId: str) -> Agent:
        """为新建群组创建 Agent 实例。

        子类可 override 此方法自定义 Agent 配置（如不同系统提示词、
        工具集）。默认使用 ChannelConfig 中的模型名和配置创建标准
        ReAct Agent，tasksDir 拼接 groupId 实现隔仓。

        Args:
            groupId: 群组唯一标识，用于拼接 tasksDir 子目录。

        Returns:
            已初始化的 Agent 实例。
        """
        agentConfig = self._config.agentConfig
        if agentConfig is None:
            from setting import Settings
            agentConfig = Settings.AgentConfig()
            agentConfig.enableWorkflow = self._config.enableWorkflow
            agentConfig.enableSchedule = self._config.enableSchedule
        agentConfig.tasksDir = os.path.join(agentConfig.tasksDir, _SanitizeGroupId(groupId))
        from agent import AgentManager
        return AgentManager.CreateAgent(self._config.modelName, agentConfig)


_SANITIZE_RE = re.compile(r'[^a-zA-Z0-9\-_.]')


def _SanitizeGroupId(groupId: str) -> str:
    """将 groupId 转为安全的文件系统目录名。

    仅保留字母、数字、连字符、下画线和点号，
    非法字符替换为 '_'，截断至 64 字符。
    """
    safe = _SANITIZE_RE.sub('_', groupId).strip(' _.-') or 'default'
    return safe[:64]
