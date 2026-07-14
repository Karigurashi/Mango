"""GroupComponent —— 群组管理组件，由 BaseChannel 直接持有。

管理多个 GroupContext，每个 GroupContext 持有独立的 Agent 实例。
Agent 创建逻辑完全内聚在此组件中，通过 channel.OnGroupCreated /
channel.OnGroupRemoved 回调通知平台层。
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING, Dict, List, Optional

from common.cancellationToken import CancellationToken
from common.logger import Logger

from ...channelComponent import IChannelComponent
from ...channelMessage import ChannelMessage
from .groupContext import GroupContext

if TYPE_CHECKING:
    from ...baseChannel import BaseChannel


_SANITIZE_RE = re.compile(r'[^a-zA-Z0-9\-_.]')


def _SanitizeGroupId(groupId: str) -> str:
    """将 groupId 转为安全的文件系统目录名。

    仅保留字母、数字、连字符、下画线和点号，
    非法字符替换为 '_'，截断至 64 字符。
    """
    safe = _SANITIZE_RE.sub('_', groupId).strip(' _.-') or 'default'
    return safe[:64]


class GroupComponent(IChannelComponent):
    """群组管理组件 —— 管理 GroupContext 集合与 Agent 创建。

    由 BaseChannel.__init__ 创建并初始化，通过 channel._groupComponent 访问。
    OnDestroy 时销毁所有群组。

    用法::

        channel = BaseChannel()
        group = channel._groupComponent.EnsureGroup("group_123", "My Group")
    """

    def __init__(self) -> None:
        self._channel: Optional[BaseChannel] = None
        self._groups: Dict[str, GroupContext] = {}

    # ---- IComponent 生命周期 ----

    def OnInitialize(self, channel: BaseChannel) -> None:
        """挂载后存储 channel 引用。"""
        self._channel = channel

    def OnDestroy(self) -> None:
        """卸载时销毁所有群组。"""
        self.DestroyAllGroups()

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

        config = self._channel._config  # type: ignore[union-attr]
        if (
            config.maxConcurrentGroups > 0
            and len(self._groups) >= config.maxConcurrentGroups
        ):
            raise RuntimeError(
                f"BaseChannel maxConcurrentGroups limit reached "
                f"({config.maxConcurrentGroups})"
            )

        agent = self._CreateAgent(groupId)
        group = GroupContext(self._channel, groupId, groupName, agent)  # type: ignore[arg-type]
        group.Start()
        self._groups[groupId] = group
        self._channel.OnGroupCreated(groupId)  # type: ignore[union-attr]
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
        group.Destroy()
        self._channel.OnGroupRemoved(groupId)  # type: ignore[union-attr]
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

    # ---- 查询 API（委托给 GroupContext，不暴露 Agent） ----

    def GetModelName(self, groupId: str) -> Optional[str]:
        """获取指定群组 Agent 使用的模型名称。

        Args:
            groupId: 群组 ID。

        Returns:
            模型名称，群组不存在时返回 None。
        """
        group = self._groups.get(groupId)
        return group.GetModelName() if group else None

    def GetActiveSessionId(self, groupId: str) -> int:
        """获取指定群组的活跃会话 ID。

        Args:
            groupId: 群组 ID。

        Returns:
            会话 ID，群组不存在时返回 0。
        """
        group = self._groups.get(groupId)
        return group.GetActiveSessionId() if group else 0

    def GetLastTokenUsage(self, groupId: str) -> tuple[int, int, float]:
        """获取指定群组最近一次推理的 Token 用量。

        Args:
            groupId: 群组 ID。

        Returns:
            (promptTokens, completionTokens, cacheHitRate)，群组不存在时返回 (0, 0, 0.0)。
        """
        group = self._groups.get(groupId)
        return group.GetLastTokenUsage() if group else (0, 0, 0.0)

    # ---- 批量销毁 ----

    def DestroyAllGroups(self) -> None:
        """销毁所有群组（供 StopAsync 调用）。

        遍历所有 GroupContext，逐一销毁并回调 OnGroupRemoved。
        """
        for groupId in list(self._groups.keys()):
            group = self._groups.pop(groupId, None)
            if group is not None:
                group.Destroy()
                self._channel.OnGroupRemoved(groupId)  # type: ignore[union-attr]

    # ---- Agent 创建（私有，完全内聚） ----

    def _CreateAgent(self, groupId: str):
        """为新建群组创建 Agent 实例（私有方法，不暴露给子类）。

        使用 ChannelConfig 中的模型名和配置创建标准 Agent，
        tasksDir 拼接 groupId 实现隔仓。

        Args:
            groupId: 群组唯一标识，用于拼接 tasksDir 子目录。

        Returns:
            已初始化的 Agent 实例。
        """
        from agent import AgentConfig, AgentManager

        config = self._channel._config  # type: ignore[union-attr]
        agentConfig = config.agentConfig
        if agentConfig is None:
            from setting import Settings
            agentConfig = Settings.AgentConfig()
        agentConfig.tasksDir = os.path.join(agentConfig.tasksDir, _SanitizeGroupId(groupId))
        return AgentManager.CreateAgent(config.modelName, agentConfig)
