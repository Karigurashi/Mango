"""WorkflowExecutor —— MAF 风格的消息驱动执行引擎。

支持 CancellationToken 协作式取消：
- 入口时设入 WorkflowContext 供节点透传给 LLM
- 每个节点执行前检查取消令牌
- asyncio.CancelledError 触发时自动 Cancel Token 以通知底层 LLM 连接关闭
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from .eExecutionStatus import EExecutionStatus
from .workflowContext import WorkflowContext
from .workflowEventBus import WorkflowEventBus
from .workflowMessage import WorkflowMessage
from .workflowStreamEvent import WorkflowStreamEvent, EStreamEventType
from common.cancellationToken import CancellationToken

if TYPE_CHECKING:
    from .baseNode import BaseNode
    from .workflow import Workflow
    from .workflowGraph import WorkflowGraph

MAX_EXECUTION_DEPTH = 5000


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
        ctx: WorkflowContext,
        eventBus: WorkflowEventBus,
        cancellationToken: CancellationToken,
    ) -> WorkflowContext:
        """异步执行工作流，从入口节点开始消息驱动遍历。

        Args:
            workflow: 工作流定义。
            ctx: 共享上下文。
            eventBus: 工作流事件总线，所有流式事件与节点状态变更均通过此总线 Push。
            cancellationToken: 取消令牌，支持协作式取消。
                asyncio.CancelledError 触发时自动 Cancel。

        Returns:
            执行后的 WorkflowContext，包含所有中间结果和输出。
        """
        ctx.SetCancellationToken(cancellationToken)
        ctx.SetEventBus(eventBus)
        ctx.SetWorkflowId(workflow.id)

        # 注入图引用，供复合节点执行子节点时使用
        graph = workflow.graph
        ctx.SetGraph(graph)

        # 通知：事件流开始
        ctx.EventBus.Push(WorkflowStreamEvent(
            workflowId=workflow.id, nodeId=0, agentId=0,
            eventType=EStreamEventType.FLOW_START,
        ))

        # 查找入口节点
        entryNodes = graph.GetEntryNodes()
        if not entryNodes:
            raise RuntimeError(
                f"Workflow '{workflow.name}': no entry node found. "
                f"Add at least one Action node with no incoming edges."
            )

        # 从每个入口并发开始执行（初始消息为空 WorkflowMessage）
        tasks = [
            WorkflowExecutor._ExecuteNodeAsync(entryId, WorkflowMessage(nodeId=0, message=""), graph, ctx)
            for entryId in entryNodes
        ]
        try:
            await asyncio.gather(*tasks)
            return ctx
        except asyncio.CancelledError:
            # 任务被取消时：Cancel Token → 底层 LLM 连接关闭 → 推送节点 cancelled
            cancellationToken.Cancel()
            for entryId in entryNodes:
                ctx.EventBus.Push(WorkflowStreamEvent(
                    workflowId=ctx.WorkflowId, nodeId=entryId, agentId=0,
                    eventType=EStreamEventType.NODE_STATUS,
                    status=EExecutionStatus.CANCELLED,
                ))
            raise
        except Exception:
            raise
        finally:
            # 最终消息：事件流结束，携带最后一个叶子节点的产出
            finalOutputs = ctx.Outputs
            text = ""
            if finalOutputs:
                text = finalOutputs[-1].message
            ctx.EventBus.Push(WorkflowStreamEvent(
                workflowId=ctx.WorkflowId, nodeId=0, agentId=0,
                eventType=EStreamEventType.FLOW_DONE,
                message=text,
            ))

    # ---- 内部执行逻辑 ----

    @staticmethod
    async def _ExecuteNodeAsync(
        nodeId: int,
        message: Any,
        graph: "WorkflowGraph",
        ctx: WorkflowContext,
        depth: int = 0,
        consumeMessages: bool = True,
    ) -> None:
        """异步执行单个 BaseNode，沿边继续遍历下游。

        Args:
            nodeId: 当前节点 ID（int）。
            message: 上游传入的消息。
            graph: 工作流图结构。
            ctx: 共享上下文。
            depth: 已废弃 —— 深度由 ctx.CurrentDepth 统一跟踪，供复合节点内嵌调用兼容保留。
            consumeMessages: 是否消费并路由子节点消息。
                Composite 节点执行子节点时传入 False，自行统一消费聚合。
        """
        executor = graph.GetNode(nodeId)
        if executor is None:
            raise RuntimeError(f"Node '{nodeId}' not found in graph.")

        # 0. 检查取消令牌（节点执行前）
        if ctx.CancellationToken and ctx.CancellationToken.IsCancellationRequested:
            ctx.EventBus.Push(WorkflowStreamEvent(
                workflowId=ctx.WorkflowId, nodeId=nodeId, agentId=0,
                eventType=EStreamEventType.NODE_STATUS,
                status=EExecutionStatus.CANCELLED,
            ))
            return

        # 1. 查找匹配的 @handler
        handlerFn = WorkflowExecutor._ResolveHandler(executor, message)
        if handlerFn is None:
            return

        # 1.5 进入节点执行：设置 CurrentNodeId，ExecutionRound +1，Depth +1
        ctx._BeginNodeExecution(nodeId)

        # 1.6 深度保护（_BeginNodeExecution 已将 ctx._currentDepth +1）
        if ctx.CurrentDepth > MAX_EXECUTION_DEPTH:
            ctx._EndNodeExecution()
            raise RecursionError(
                f"Workflow execution exceeded max depth {MAX_EXECUTION_DEPTH}. "
                f"Possible infinite loop at node '{nodeId}'."
            )

        # 2. 通知：节点开始执行
        ctx.EventBus.Push(WorkflowStreamEvent(
            workflowId=ctx.WorkflowId, nodeId=nodeId, agentId=0,
            eventType=EStreamEventType.NODE_STATUS,
            status=EExecutionStatus.RUNNING,
        ))

        try:
            # 2.5 注入上下文到节点实例（供 handler 通过 self.context 访问）
            executor.context = ctx

            # 3. 调用 handler
            await handlerFn(executor, message)
            # 通知：节点执行完成
            ctx.EventBus.Push(WorkflowStreamEvent(
                workflowId=ctx.WorkflowId, nodeId=nodeId, agentId=0,
                eventType=EStreamEventType.NODE_STATUS,
                status=EExecutionStatus.COMPLETED,
            ))
        except asyncio.CancelledError:
            # 任务被取消：通知取消状态，然后重新抛出让上层处理
            ctx.EventBus.Push(WorkflowStreamEvent(
                workflowId=ctx.WorkflowId, nodeId=nodeId, agentId=0,
                eventType=EStreamEventType.NODE_STATUS,
                status=EExecutionStatus.CANCELLED,
            ))
            raise
        except Exception:
            # 通知：节点执行失败
            ctx.EventBus.Push(WorkflowStreamEvent(
                workflowId=ctx.WorkflowId, nodeId=nodeId, agentId=0,
                eventType=EStreamEventType.NODE_STATUS,
                status=EExecutionStatus.FAILED,
            ))
            raise
        finally:
            ctx._EndNodeExecution()

        # 4. 消费 ctx 中的待发送消息，路由到下游
        if consumeMessages:
            pendingMessages = ctx.ConsumeMessages()
            for msg, targetIds in pendingMessages:
                if targetIds:
                    targets = targetIds
                else:
                    # 默认路由：所有 OUT 类型下游边指向的节点
                    targets = [e.toNodeId for e in graph.GetOutEdgesFrom(nodeId)]

                if targets:
                    tasks = [
                        WorkflowExecutor._ExecuteNodeAsync(tid, msg, graph, ctx)
                        for tid in targets
                    ]
                    await asyncio.gather(*tasks)
                else:
                    # 叶子节点消息，无下游路由 → 最终产出
                    ctx._outputs.append(msg)

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
