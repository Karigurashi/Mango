"""BaseChannel —— 多群消息路由框架基类。

直接持有 GroupComponent（群组管理）和 CommandComponent（指令系统），
子类可在 __init__ 中创建自定义组件扩展能力。

内置指令系统：消息内容以指定前缀字符开头时，走指令分发而非 Agent 执行。
子类通过 _commandComponent.RegisterCommand 注册指令、override CreateCommandContext 提供平台上下文。

Agent 完全封装在 Channel 内部：子类无法获取 Agent 实例或其组件，
所有 Agent 相关操作通过 GroupContext 的查询方法完成。

架构概览::

    ┌─────────────────────────────────────────────┐
    │                BaseChannel                   │
    │  _groupComponent   _commandComponent         │
    │  ┌─────────────┐  ┌──────────────┐          │
    │  │ GroupComp   │  │ CommandComp  │          │
    │  │  Groups     │  │  Registry    │          │
    │  │  Agent 创建  │  │  Dispatch    │          │
    │  └─────────────┘  └──────────────┘          │
    │  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
    │  │ GroupCtx │  │ GroupCtx │  │ GroupCtx │  │
    │  │  Agent A │  │  Agent B │  │  Agent C │  │
    │  └──────────┘  └──────────┘  └──────────┘  │
    └─────────────────────────────────────────────┘

入站消息流:
  普通消息:  Platform → ChannelMessage → ReceiveMessageAsync
             → _groupComponent.EnsureGroup → _DispatchAgentMessageAsync
             → GroupContext.PostMessage（非阻塞，入队群线程）
             → 群线程: Agent.RunStreamAsync → EventBus 事件
             → GroupContext._OnAgentEvent → OnAgentEventSync
             → 平台自行处理（累积 / 流式转发 / 投递响应）

  指令消息:  Platform → ChannelMessage → ReceiveMessageAsync
             → content.startswith(prefix) → _commandComponent.DispatchAsync
             → CommandRegistry.DispatchAsync → Command.handler(ctx, args)
             → ctx 响应缓冲区 → OnSendResponseAsync 投递

  CLI 覆盖:  CliApp._DispatchAgentMessageAsync → GroupContext.SendMessageAsync
             （阻塞，在主事件循环中直接 await Agent，用户等待响应）
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from common.cancellationToken import CancellationToken
from common.logger import Logger

from .channelConfig import ChannelConfig
from .channelMessage import ChannelMessage
from .component.command import CommandComponent, CommandContext
from .component.group import GroupComponent, GroupContext
from .eChannelState import EChannelState

if TYPE_CHECKING:
    from agent import AgentStreamEvent


class BaseChannel:
    """多群消息路由框架基类 —— 直接持有 GroupComponent 和 CommandComponent。

    管理多个 GroupContext（通过 GroupComponent），每个 GroupContext 持有独立的 Agent 实例。
    Agent 完全封装在 GroupContext 内部，子类无法直接访问。

    内置指令系统（通过 CommandComponent）：消息内容以 commandPrefix 开头时走指令分发。
    子类通过 _commandComponent.RegisterCommand 注册指令、override CreateCommandContext
    提供平台特定的上下文（如 CLI 的即时终端输出）。

    子类需实现:
        - OnAgentEventSync: 接收 Agent 事件并自行处理（累积 / 流式转发 / 投递）（必需）。
        - OnStartAsync / OnStopAsync: 平台启动 / 停止逻辑（可选）。
        - OnSendResponseAsync: 响应投递便捷方法，供 OnAgentEventSync 内部调用（可选）。
        - CreateCommandContext: 自定义指令上下文（可选）。

    子类扩展新功能时，在 __init__ 中创建自定义组件::

        class FeishuChannel(BaseChannel):
            def __init__(self, config=None):
                super().__init__(...)
                self._cardComponent = FeishuCardComponent()
                self._cardComponent.OnInitialize(self)

    Usage::

        channel = FeishuChannel(ChannelConfig(modelName="deepseek-chat"))
        await channel.StartAsync()

        msg = ChannelMessage(groupId="group_123", userId="user_456", content="你好")
        await channel.ReceiveMessageAsync(msg)
    """

    def __init__(self, config: Optional[ChannelConfig] = None) -> None:
        self._config: ChannelConfig = config or ChannelConfig()
        self._state: EChannelState = EChannelState.STOPPED

        # ---- 内置组件 ----
        self._groupComponent: GroupComponent = GroupComponent()
        self._groupComponent.OnInitialize(self)
        self._commandComponent: CommandComponent = CommandComponent()
        self._commandComponent.OnInitialize(self)

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

        # 销毁组件
        self._groupComponent.OnDestroy()
        self._commandComponent.OnDestroy()

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

    def OnGroupCreated(self, groupId: str) -> None:
        """新群创建回调，子类可 override 进行平台注册。

        Args:
            groupId: 新创建的群组 ID。
        """
        pass

    def OnGroupRemoved(self, groupId: str) -> None:
        """群移除回调，子类可 override 进行平台清理。

        Args:
            groupId: 被移除的群组 ID。
        """
        pass

    # ---- 指令上下文工厂（子类可 override） ----

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
        return CommandContext(self, groupContext, message, self._commandComponent.CommandRegistry)

    # ---- 属性 ----

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

        消息内容以 commandPrefix 开头时走指令分发流程（CommandComponent.DispatchAsync），
        否则通过 _DispatchAgentMessageAsync 分发到 Agent。

        默认 _DispatchAgentMessageAsync 调用 GroupContext.PostMessage（非阻塞），
        Agent 在群线程中执行，主事件循环不被阻塞。
        CLI 等单群交互式 Channel 可 override _DispatchAgentMessageAsync 改为阻塞模式。

        Args:
            message: 标准化入站消息。
            cancellationToken: 取消令牌。
        """
        group = self._groupComponent.EnsureGroup(message.groupId, message.groupName)

        content = message.content
        if content and content.startswith(self._config.commandPrefix):
            await self._commandComponent.DispatchAsync(group, message, cancellationToken)
        else:
            await self._DispatchAgentMessageAsync(group, message, cancellationToken)

    async def _DispatchAgentMessageAsync(
        self,
        group: GroupContext,
        message: ChannelMessage,
        cancellationToken: Optional[CancellationToken] = None,
    ) -> None:
        """将消息分发到 Agent（子类可 override）。

        默认实现: 调用 GroupContext.PostMessage（非阻塞），消息入队群线程，
        Agent 在群线程的独立事件循环中串行执行。适用于多群 Channel（飞书），
        主事件循环不被 Agent 推理阻塞。

        CLI 等单群交互式 Channel 可 override 此方法改为阻塞模式::

            async def _DispatchAgentMessageAsync(self, group, message, token):
                await group.SendMessageAsync(message, token)  # 阻塞，用户等待响应

        Args:
            group: 目标群组上下文。
            message: 标准化入站消息。
            cancellationToken: 取消令牌。
        """
        group.PostMessage(message, cancellationToken)
