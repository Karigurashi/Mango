"""子Agent 上下文管理 —— 支持 isolated 和 fork 两种上下文继承模式。"""

from __future__ import annotations

from common.const import ERole

from .eSubagentContextMode import ESubagentContextMode
from .eContextLodLevel import EContextLodLevel
from .session import Session


class SubagentContext:
    """管理子 Agent 的上下文生命周期。

    支持两种模式：
    - ISOLATED: 子Agent 从空白上下文开始，仅继承父 Agent 的 LOD 0 System Prompt
    - FORK: 复制父 Agent 全部消息 + LOD 标记，子Agent 独立压缩

    Usage::

        subCtx = SubagentContext()
        childSession = await subCtx.PrepareSpawnAsync(
            parentSession, ESubagentContextMode.FORK
        )
        # ... 子Agent 使用 childSession 运行 ...
        await subCtx.EndSubagentAsync(childSession, parentSession)
    """

    async def PrepareSpawnAsync(
        self,
        parentSession: Session,
        mode: ESubagentContextMode,
    ) -> Session:
        """准备子Agent 的 Session。

        Args:
            parentSession: 父 Agent 的 Session。
            mode: 上下文继承模式。

        Returns:
            子Agent 的新 Session。
        """
        childSession = Session()

        if mode == ESubagentContextMode.ISOLATED:
            for msg in parentSession.GetAll():
                if (
                    msg.role == ERole.SYSTEM
                    and msg.lodLevel == EContextLodLevel.RESIDENT
                ):
                    childSession.Append(msg.Clone())
        elif mode == ESubagentContextMode.FORK:
            for msg in parentSession.GetAll():
                childSession.Append(msg.Clone())
            childSession._forkBaselineCount = len(childSession.GetAll())

        return childSession

    async def EndSubagentAsync(
        self,
        childSession: Session,
        parentSession: Session,
        mergeResults: bool = True,
    ) -> None:
        """子Agent 结束后清理。

        Args:
            childSession: 子Agent 的 Session。
            parentSession: 父 Agent 的 Session。
            mergeResults: 是否将子Agent 的关键结果合并回父 Session。
        """
        if mergeResults:
            newMessages = childSession.GetAll()[childSession._forkBaselineCount :]
            for msg in newMessages:
                if msg.isCompacted:
                    continue
                if msg.role == ERole.SYSTEM:
                    continue
                if msg.lodLevel.value <= EContextLodLevel.SUMMARIZABLE.value:
                    merged = msg.Clone()
                    merged.metadata = {
                        **merged.metadata,
                        "fromSubagent": True,
                    }
                    parentSession.Append(merged)

        childSession.Clear()

    def __repr__(self) -> str:
        return "SubagentContext()"
