"""并行节点 —— 并行执行所有子节点，全部完成后向下游广播。"""

import asyncio

from ...core.baseNode import BaseNode, handler
from ...core.eNodeCategory import ENodeCategory
from ...core.nodeRegistry import NodeRegistry
from ...core.workflowExecutor import WorkflowExecutor


@NodeRegistry.Register
class ParallelNode(BaseNode):
    """并行执行 —— 并行执行所有子节点，全部完成后继续。

    Config: 无。
    """

    nodeType = "Composite/Parallel"
    category = ENodeCategory.COMPOSITE
    displayName = "Parallel"
    description = "并行执行所有子节点，全部完成后继续"

    @classmethod
    def GetConfigSchema(cls) -> list[dict]:
        return []

    @handler
    async def Handle(self, message) -> None:
        """并行执行所有子节点，全部完成后向下游广播消息。"""
        graph = self.context.Graph
        if graph is None:
            await self.context.SendMessageAsync(message)
            return

        subEdges = graph.GetSubNodeEdgesFrom(self.context.CurrentNodeId)
        if not subEdges:
            await self.context.SendMessageAsync(message)
            return

        onNodeEvent = self.context.OnNodeEvent
        tasks = [
            WorkflowExecutor._ExecuteNodeAsync(
                edge.toNodeId,
                message,
                graph,
                self.context,
                depth=0,
                onNodeEvent=onNodeEvent,
            )
            for edge in subEdges
        ]
        await asyncio.gather(*tasks)

        # 所有子节点执行完毕后，向下游广播
        await self.context.SendMessageAsync(message)
