"""条件分支节点 —— 根据布尔条件选择执行路径。"""

from ...core.baseNode import BaseNode, handler
from ...core.eNodeCategory import ENodeCategory
from ...core.nodeRegistry import NodeRegistry


@NodeRegistry.Register
class BranchNode(BaseNode):
    """条件分支 —— 根据条件值决定下游路径。

    Config:
        Condition: 条件值（bool，默认 False）。

    下游通过 WorkflowExecutor 按边路由，本节点通过 SendMessageAsync 指定目标。
    """

    nodeType = "Condition/Branch"
    category = ENodeCategory.CONDITION
    displayName = "Branch"
    description = "根据条件值决定执行哪个分支"

    @classmethod
    def GetConfigSchema(cls) -> list[dict]:
        return [
            {"name": "Condition", "type": "bool", "default": False, "description": "条件值"},
        ]

    @handler
    async def Handle(self, message) -> None:
        """根据 self.Condition 或上游消息中的 condition 决定路由。

        实际分支路由由执行引擎根据边的 condition 回调完成，
        此处简化为透传消息给所有下游。
        """
        await self.context.SendMessageAsync(message)
