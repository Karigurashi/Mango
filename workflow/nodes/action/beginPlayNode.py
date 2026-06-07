"""入口事件节点 —— 工作流执行的起点。"""

from ...core.baseNode import BaseNode, handler
from ...core.eNodeCategory import ENodeCategory
from ...core.nodeRegistry import NodeRegistry


@NodeRegistry.Register
class BeginPlayNode(BaseNode):
    """工作流入门 —— 无入边，执行时首先触发，向所有下游节点广播消息。"""

    nodeType = "Action/BeginPlay"
    category = ENodeCategory.ACTION
    displayName = "Begin Play"
    description = "工作流入门，开始执行时触发"

    @classmethod
    def GetConfigSchema(cls) -> list[dict]:
        return []

    @handler
    async def Handle(self, message) -> None:
        """向所有下游节点发送空消息，启动工作流。"""
        await self.context.SendMessageAsync(None)
