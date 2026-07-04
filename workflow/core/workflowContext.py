"""WorkflowContext —— MAF 风格的类型安全执行上下文，替代 Blackboard。

提供消息传递（SendMessageAsync）、输出产出（YieldOutputAsync）和 KV 变量存储，
以及 CancellationToken 取消令牌传递。
"""

from __future__ import annotations

from typing import Any, Optional, TYPE_CHECKING

from .workflowMessage import WorkflowMessage

if TYPE_CHECKING:
    from common.cancellationToken import CancellationToken
    from .workflowGraph import WorkflowGraph
    from .workflowEventBus import WorkflowEventBus


class WorkflowContext:
    """MAF 风格的 WorkflowContext，承载工作流执行期间的运行时状态。

    用法::

        ctx = WorkflowContext()
        ctx.Set("var.Count", 0)
        await ctx.SendMessageAsync({"text": "hello"})
        await ctx.YieldOutputAsync("done")

    节点可通过 ctx.CancellationToken 获取取消令牌并透传给 LLM 调用。
    流式事件通过 ctx.EventBus 同步推送。
    """

    def __init__(self, initialData: dict[str, Any] | None = None) -> None:
        self._data: dict[str, Any] = initialData.copy() if initialData else {}
        self._pendingMessages: list[tuple[WorkflowMessage, list[int] | None]] = []
        self._outputs: list[WorkflowMessage] = []
        self._cancellationToken: Optional["CancellationToken"] = None
        self._currentNodeId: int = 0
        self._executionRound: int = 0
        self._eventBus: Optional["WorkflowEventBus"] = None
        self._graph: Optional["WorkflowGraph"] = None
        self._currentDepth: int = 0
        self._workflowId: int = 0

    # ---- KV 存储 ----

    def Get(self, key: str, default: Any = None) -> Any:
        """读取键值。"""
        return self._data.get(key, default)

    def Set(self, key: str, value: Any) -> None:
        """写入键值。"""
        self._data[key] = value

    def Has(self, key: str) -> bool:
        """检查键是否存在。"""
        return key in self._data

    def Remove(self, key: str) -> None:
        """删除键。"""
        self._data.pop(key, None)

    def GetAll(self) -> dict[str, Any]:
        """返回所有数据的浅拷贝。"""
        return dict(self._data)

    def Merge(self, other: dict[str, Any]) -> None:
        """批量合并数据。"""
        self._data.update(other)

    # ---- 消息传递 ----

    async def SendMessageAsync(self, message: WorkflowMessage, targetIds: list[int] | None = None) -> None:
        """向下游节点发送消息。

        Args:
            message: 要发送的 WorkflowMessage。
            targetIds: 目标节点 ID 列表（int），None 表示广播到所有下游。
        """
        self._pendingMessages.append((message, targetIds))

    def ConsumeMessages(self) -> list[tuple[WorkflowMessage, list[int] | None]]:
        """消费所有待发送消息（执行引擎使用）。"""
        messages = self._pendingMessages
        self._pendingMessages = []
        return messages

    # ---- 产出 ----

    async def YieldOutputAsync(self, output: Any) -> None:
        """产出工作流最终输出。"""
        self._outputs.append(output)

    @property
    def Outputs(self) -> list[WorkflowMessage]:
        """获取所有已产出输出。"""
        return list(self._outputs)

    # ---- 取消令牌 ----

    @property
    def CancellationToken(self) -> Optional["CancellationToken"]:
        """当前工作流的取消令牌，节点可用此令牌中断 LLM 调用。

        由 WorkflowExecutor 在执行前注入。
        """
        return self._cancellationToken

    def SetCancellationToken(self, token: "CancellationToken") -> None:
        """注入取消令牌（仅 WorkflowExecutor 调用）。"""
        self._cancellationToken = token

    # ---- 图引用 ----

    @property
    def Graph(self) -> Optional["WorkflowGraph"]:
        """当前执行的 WorkflowGraph 引用，供节点访问图结构（子节点等）。

        由 WorkflowExecutor 在执行前注入。
        """
        return self._graph

    def SetGraph(self, graph: "WorkflowGraph") -> None:
        """注入图引用（仅 WorkflowExecutor 调用）。"""
        self._graph = graph

    # ---- 运行时状态 ----

    @property
    def CurrentNodeId(self) -> int:
        """当前正在执行的节点 ID（由 WorkflowExecutor 在执行前设置）。"""
        return self._currentNodeId

    @property
    def ExecutionRound(self) -> int:
        """当前执行轮次（任意节点每执行一次 +1）。"""
        return self._executionRound

    # ---- 事件总线 ----

    @property
    def WorkflowId(self) -> int:
        """当前所属工作流 ID，由 WorkflowExecutor 在执行前注入。"""
        return self._workflowId

    def SetWorkflowId(self, workflowId: int) -> None:
        """注入工作流 ID（仅 WorkflowExecutor 调用）。"""
        self._workflowId = workflowId

    @property
    def EventBus(self) -> Optional["WorkflowEventBus"]:
        """工作流级同步事件总线，由 WorkflowExecutor 在执行前注入。

        节点可通过此总线同步推送流式事件（thinking / content chunk 等），
        无需 asyncio.create_task 桥接。
        """
        return self._eventBus

    def SetEventBus(self, eventBus: "WorkflowEventBus") -> None:
        """注入事件总线（仅 WorkflowExecutor 调用）。"""
        self._eventBus = eventBus

    @property
    def CurrentDepth(self) -> int:
        """当前执行深度（每进入子节点 +1，退出 -1），用于防止无限嵌套。"""
        return self._currentDepth

    def _BeginNodeExecution(self, nodeId: int) -> int:
        """进入节点执行：设置当前节点 ID，全局轮次 +1，深度 +1（仅 WorkflowExecutor 调用）。"""
        self._currentNodeId = nodeId
        self._executionRound += 1
        self._currentDepth += 1
        return self._executionRound

    def _EndNodeExecution(self) -> None:
        """退出节点执行：深度 -1（仅 WorkflowExecutor 调用）。"""
        self._currentDepth -= 1

    # ---- 魔法方法 ----

    def __repr__(self) -> str:
        return f"WorkflowContext(data={len(self._data)} keys, pending={len(self._pendingMessages)}, outputs={len(self._outputs)})"

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def __len__(self) -> int:
        return len(self._data)
