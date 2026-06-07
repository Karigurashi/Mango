"""WorkflowExecutor —— MAF 风格的消息驱动执行引擎。

支持 CancellationToken 协作式取消：
- 入口时设入 WorkflowContext 供节点透传给 LLM
- 每个节点执行前检查取消令牌
- asyncio.CancelledError 触发时自动 Cancel Token 以通知底层 LLM 连接关闭
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Optional

from .eExecutionStatus import EExecutionStatus
from .workflowContext import WorkflowContext, NodeStreamCallback
from common.cancellationToken import CancellationToken

if TYPE_CHECKING:
    from .baseNode import BaseNode
    from .workflow import Workflow
    from .workflowGraph import WorkflowGraph

MAX_EXECUTION_DEPTH = 5000

# 执行事件回调签名
NodeEventCallback = Callable[[int, EExecutionStatus], Awaitable[None]]


class WorkflowExecutor:
    """消息驱动执行引擎，沿有向边遍历图结构，通过 @handler 类型路由调用节点。

    用法::

        wf = Workflow.FromJson(jsonData)
        ctx = WorkflowContext()
        await WorkflowExecutor.ExecuteAsync(wf, ctx)
    """

    # ---- 公开接口 ----

    @staticmethod
    async def ExecuteAsync(
        workflow: "Workflow",
        ctx: WorkflowContext | None = None,
        onNodeEvent: Optional[NodeEventCallback] = None,
        onNodeStream: Optional[NodeStreamCallback] = None,
        cancellationToken: Optional[CancellationToken] = None,
    ) -> WorkflowContext:
        """异步执行工作流，从入口节点开始消息驱动遍历。

        Args:
            workflow: 工作流定义。
            ctx: 外部传入的上下文（可选），不传则自动创建。
            onNodeEvent: 节点执行事件回调 async(nodeId, status)。
                status 取值: EExecutionStatus 枚举成员。
            onNodeStream: 节点流式输出回调 async(nodeId, eventType, data)。
                eventType 取值: EStreamEventType 枚举成员。
            cancellationToken: 取消令牌（可选），支持协作式取消。
                未提供时自动创建，asyncio.CancelledError 触发时自动 Cancel。

        Returns:
            执行后的 WorkflowContext，包含所有中间结果和输出。
        """
        if ctx is None:
            ctx = WorkflowContext()

        # 取消令牌：外部传入 > 自动创建
        if cancellationToken is None:
            cancellationToken = CancellationToken()
        ctx.SetCancellationToken(cancellationToken)

        # 设置流式回调
        if onNodeStream is not None:
            ctx.SetNodeStreamCallback(onNodeStream)

        # 注入图引用和事件回调，供复合节点执行子节点时使用
        graph = workflow.graph
        ctx.SetGraph(graph)
        if onNodeEvent is not None:
            ctx.SetOnNodeEvent(onNodeEvent)

        # 查找入口节点
        entryNodes = graph.GetEntryNodes()
        if not entryNodes:
            raise RuntimeError(
                f"Workflow '{workflow.name}': no entry node found. "
                f"Add at least one Action node with no incoming edges."
            )

        # 从每个入口并发开始执行（初始消息为 None）
        tasks = [
            WorkflowExecutor._ExecuteNodeAsync(
                entryId, None, graph, ctx, depth=0, onNodeEvent=onNodeEvent
            )
            for entryId in entryNodes
        ]
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            # 任务被取消时：Cancel Token → 底层 LLM 连接关闭 → 标记节点 cancelled
            cancellationToken.Cancel()
            if onNodeEvent:
                for entryId in entryNodes:
                    await onNodeEvent(entryId, EExecutionStatus.CANCELLED)
            raise

        return ctx

    # ---- 内部执行逻辑 ----

    @staticmethod
    async def _ExecuteNodeAsync(
        nodeId: int,
        message: Any,
        graph: "WorkflowGraph",
        ctx: WorkflowContext,
        depth: int = 0,
        onNodeEvent: Optional[NodeEventCallback] = None,
    ) -> None:
        """异步执行单个 BaseNode，沿边继续遍历下游。

        Args:
            nodeId: 当前节点 ID（int）。
            message: 上游传入的消息。
            graph: 工作流图结构。
            ctx: 共享上下文。
            depth: 当前递归深度。
            onNodeEvent: 节点执行事件回调。
        """
        if depth > MAX_EXECUTION_DEPTH:
            raise RecursionError(
                f"Workflow execution exceeded max depth {MAX_EXECUTION_DEPTH}. "
                f"Possible infinite loop at node '{nodeId}'."
            )

        executor = graph.GetNode(nodeId)
        if executor is None:
            raise RuntimeError(f"Node '{nodeId}' not found in graph.")

        # 0. 检查取消令牌（节点执行前）
        if ctx.CancellationToken and ctx.CancellationToken.IsCancellationRequested:
            if onNodeEvent:
                await onNodeEvent(nodeId, EExecutionStatus.CANCELLED)
            return

        # 1. 查找匹配的 @handler
        handlerFn = WorkflowExecutor._ResolveHandler(executor, message)
        if handlerFn is None:
            return

        # 1.5 进入节点执行：设置 CurrentNodeId，ExecutionRound +1
        ctx._BeginNodeExecution(nodeId)

        # 2. 通知：节点开始执行
        if onNodeEvent:
            await onNodeEvent(nodeId, EExecutionStatus.RUNNING)

        try:
            # 2.5 注入上下文到节点实例（供 handler 通过 self.context 访问）
            executor.context = ctx

            # 3. 调用 handler
            await handlerFn(executor, message)
            # 通知：节点执行完成
            if onNodeEvent:
                await onNodeEvent(nodeId, EExecutionStatus.COMPLETED)
        except asyncio.CancelledError:
            # 任务被取消：通知取消状态，然后重新抛出让上层处理
            if onNodeEvent:
                await onNodeEvent(nodeId, EExecutionStatus.CANCELLED)
            raise
        except Exception:
            # 通知：节点执行失败
            if onNodeEvent:
                await onNodeEvent(nodeId, EExecutionStatus.FAILED)
            raise

        # 4. 消费 ctx 中的待发送消息，路由到下游
        pendingMessages = ctx.ConsumeMessages()
        for msg, targetIds in pendingMessages:
            if targetIds:
                targets = targetIds
            else:
                # 默认路由：所有 OUT 类型下游边指向的节点
                targets = [e.toNodeId for e in graph.GetOutEdgesFrom(nodeId)]

            if targets:
                tasks = [
                    WorkflowExecutor._ExecuteNodeAsync(
                        tid, msg, graph, ctx, depth + 1, onNodeEvent=onNodeEvent
                    )
                    for tid in targets
                ]
                await asyncio.gather(*tasks)

    @staticmethod
    def _ResolveHandler(executor: "BaseNode", message: Any) -> callable | None:
        """根据消息类型解析对应的 @handler 方法。

        Args:
            executor: BaseNode 实例。
            message: 上游传入的消息。

        Returns:
            匹配的 handler 方法，无匹配返回 None。
        """
        handlers = executor._GetHandlers()

        if not handlers:
            # 无 @handler：回退到 ExecuteAsync（兼容）
            if hasattr(executor, "ExecuteAsync"):
                return executor.ExecuteAsync
            return None

        # 只有一个 handler：直接返回
        if len(handlers) == 1:
            return next(iter(handlers.values()))

        # 多个 handler：按 input type 匹配
        if message is None:
            defaultHandler = handlers.get(type(None)) or handlers.get(None)
            if defaultHandler:
                return defaultHandler

        msgType = type(message)
        for inputType, handlerMethod in handlers.items():
            if inputType is not None and issubclass(msgType, inputType):
                return handlerMethod

        # 回退到默认 handler（@handler 无 inputType）
        if None in handlers:
            return handlers[None]

        return None
