"""WorkflowComponent —— 后台 Workflow 任务管理器，可挂载到 BaseAgent。

管理 Workflow 的异步生命周期：启动、列表查询、取消、完成推送。
通过监听 WorkflowEventBus.FLOW_DONE 感知完成，直接驱动 Agent 继续对话。
"""

from __future__ import annotations

import asyncio
import json as _json
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from agent.core.baseComponent import IComponent
from agent.component.data.dataComponent import DataComponent
from agent.component.data.eAgentState import EAgentState
from agent.component.eventBus.agentStreamEvent import EAgentStreamEventType
from common.cancellationToken import CancellationToken
from workflow.workflow import EWorkflowStatus
from workflow.core.workflowStreamEvent import EStreamEventType

if TYPE_CHECKING:
    from agent.core.baseAgent import BaseAgent
    from agent.component.eventBus.agentStreamEvent import AgentStreamEvent
    from agent.component.eventBus.eventBusComponent import EventBusComponent
    from workflow import Workflow
    from workflow.core.workflowStreamEvent import WorkflowStreamEvent


MAX_WORKFLOWS = 10


@dataclass(slots=True)
class WorkflowTaskInfo:
    """单个后台 Workflow 任务的运行时元数据。"""

    workflowId: int
    name: str
    createdAt: int
    lastAccessedAt: float = 0.0
    task: asyncio.Task | None = None
    cancellationToken: Any = None  # CancellationToken
    workflow: Any = None  # Workflow 实例引用，供完成时收集结果
    result: dict | None = None
    error: str | None = None


@dataclass(slots=True)
class LaunchResult:
    """Launch() 返回的确定对象。"""

    workflowId: int
    status: EWorkflowStatus
    name: str


class WorkflowComponent(IComponent):
    """后台 Workflow 任务管理器，每个 Agent 实例持有一个。

    监听 WorkflowEventBus.FLOW_DONE 感知完成：
    - Agent 非活跃 → 立即调用 RunStreamAsync 继续对话
    - Agent 正活跃 → 暂存，监听 EventBusComponent.DONE 后批量触发
    """

    # ---- IComponent 生命周期 ----

    def OnInitialize(self, agent: BaseAgent) -> None:
        self._agent: BaseAgent = agent
        self._taskRegistry: dict[int, WorkflowTaskInfo] = {}
        self._pendingInjects: list[int] = []  # 等待 DONE 后触发的 workflowId
        self._eventLogs: dict[int, list[dict]] = {}  # workflowId -> 节点事件日志
        self._maxWorkflows: int = MAX_WORKFLOWS

        # 监听 Agent DONE 事件，批量触发 pending 结果
        from agent.component.eventBus.eventBusComponent import EventBusComponent
        eventBus = agent.GetComponent(EventBusComponent)
        eventBus.AddListener(self._OnAgentEvent)

        # 获取 StoreComponent 引用，用于结果落盘
        from agent.component.store.storeComponent import StoreComponent
        self._storeComp = agent.GetComponent(StoreComponent)

    def OnDestroy(self) -> None:
        for info in self._taskRegistry.values():
            if info.task is not None and not info.task.done():
                info.task.cancel()
        self._taskRegistry.clear()
        self._pendingInjects.clear()

    # ---- 公开接口（供工具通过 GetComponent 调用） ----

    def Launch(self, jsonStr: str) -> LaunchResult:
        """启动一个后台 Workflow，立即返回 workflowId。

        Args:
            jsonStr: Workflow JSON 字符串。

        Returns:
            _LaunchResult 包含 workflowId、status、name。
        """
        from workflow import Workflow

        wf = Workflow.FromJson(jsonStr)
        workflowId = wf.id

        # LRU: 超出容量则淘汰最久未访问的 workflow
        while len(self._taskRegistry) >= self._maxWorkflows:
            self._EvictLRU()

        cancellationToken = CancellationToken()
        info = WorkflowTaskInfo(
            workflowId=workflowId,
            name=wf.name or "Unnamed",
            createdAt=int(time.time()),
            lastAccessedAt=time.time(),
            cancellationToken=cancellationToken,
            workflow=wf,
        )

        # 订阅 WorkflowEventBus 感知完成
        wf.eventBus.AddListener(self._OnWorkflowEvent)

        # 后台执行
        info.task = asyncio.create_task(
            self._RunWorkflowAsync(workflowId, wf, cancellationToken)
        )
        self._taskRegistry[workflowId] = info
        return LaunchResult(
            workflowId=workflowId,
            status=wf.status,
            name=info.name,
        )

    def ListWorkflows(self) -> list[dict]:
        """列出当前 Agent 管理的所有 Workflow 及其状态。"""
        results: list[dict] = []
        for info in self._taskRegistry.values():
            self._BumpAccess(info.workflowId)
            item: dict = {
                "workflowId": info.workflowId,
                "name": info.name,
                "status": info.workflow.status.name,
                "createdAt": info.createdAt,
            }
            if info.result is not None:
                item["result"] = info.result
            if info.error is not None:
                item["error"] = info.error
            results.append(item)
        return results

    def Cancel(self, workflowId: int) -> bool:
        """取消指定 Workflow。

        Returns:
            是否成功发起取消（仅 running 状态可取消）。
        """
        info = self._taskRegistry.get(workflowId)
        if info is None or info.workflow.status != EWorkflowStatus.RUNNING:
            return False
        if info.cancellationToken is not None:
            info.cancellationToken.Cancel()
        info.workflow.status = EWorkflowStatus.CANCELLED
        self._BumpAccess(workflowId)
        return True

    # ---- 后台执行 ----

    async def _RunWorkflowAsync(
        self, workflowId: int, wf: Workflow, cancellationToken: CancellationToken
    ) -> None:
        """后台执行 Workflow，异常由 WorkflowEventBus.FLOW_DONE 监听器统一处理。"""
        try:
            await wf.ExecuteAsync(cancellationToken=cancellationToken)
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    # ---- WorkflowEventBus 监听 ----

    def _OnWorkflowEvent(self, event: WorkflowStreamEvent) -> None:
        """WorkflowEventBus 事件回调。

        收集所有 NODE_STATUS / AI_CONTENT 事件到日志，
        FLOW_DONE 时汇总写入 ContentStore 并驱动 Agent 继续对话。
        """
        workflowId = event.workflowId

        if event.eventType != EStreamEventType.FLOW_DONE:
            if workflowId not in self._eventLogs:
                self._eventLogs[workflowId] = []
            self._eventLogs[workflowId].append({
                "type": event.eventType.name,
                "nodeId": event.nodeId,
                "status": event.status.name if event.status else None,
                "message": event.message,
            })
            return

        info = self._taskRegistry.get(workflowId)
        if info is None:
            return

        self._BumpAccess(workflowId)

        # 已取消的跳过
        if info.workflow.status == EWorkflowStatus.CANCELLED:
            self._eventLogs.pop(workflowId, None)
            return

        # 汇总所有节点事件 → 写入 ContentStore → 拼入结果
        summary = self._BuildWorkflowSummary(workflowId, info)
        filePath = self._PersistSummary(summary)

        resultContent = event.message if event.message else summary[:500]
        info.result = {
            "summary": summary,
            "filePath": filePath,
            "content": resultContent,
        }
        self._eventLogs.pop(workflowId, None)

        if self._IsAgentRunning():
            self._pendingInjects.append(workflowId)
        else:
            self._InjectResult(workflowId)

    # ---- 汇总与落盘 ----

    def _BuildWorkflowSummary(self, workflowId: int, info: WorkflowTaskInfo) -> str:
        """将事件日志按行输出。"""
        events = self._eventLogs.get(workflowId, [])
        lines: list[str] = []
        for ev in events:
            nodeId = ev["nodeId"]
            evType = ev["type"]
            status = ev.get("status") or ""
            message = ev.get("message") or ""
            parts = [f"[Node-{nodeId}]", evType]
            if status:
                parts.append(status)
            if message:
                parts.append(message)
            lines.append(" ".join(parts))
        return "\n".join(lines)

    def _PersistSummary(self, summary: str) -> str | None:
        """将摘要写入 StoreComponent，返回文件路径。"""
        path = self._storeComp.Store(summary)
        return path

    # ---- Agent DONE 监听 ----

    def _OnAgentEvent(self, event: AgentStreamEvent) -> None:
        if event.eventType == EAgentStreamEventType.DONE:
            self._FlushPendingInjects()

    def _FlushPendingInjects(self) -> None:
        """Agent 本轮结束，批量触发 Agent 继续对话。"""
        pending = self._pendingInjects[:]
        self._pendingInjects.clear()
        if not pending:
            return

        results: list[dict] = []
        for workflowId in pending:
            info = self._taskRegistry.get(workflowId)
            if info is None:
                continue
            results.append(self._BuildInjectPayload(info))
        if not results:
            return
        content = _json.dumps(
            results[0] if len(results) == 1 else {"completedWorkflows": results},
            ensure_ascii=False,
        )
        asyncio.create_task(self._agent.RunStreamAsync(content))

    # ---- 结果注入 ----

    def _InjectResult(self, workflowId: int) -> None:
        """将 workflow 结果作为 USER 消息触发 Agent 继续对话。"""
        info = self._taskRegistry.get(workflowId)
        if info is None:
            return

        content = _json.dumps(self._BuildInjectPayload(info), ensure_ascii=False)
        asyncio.create_task(self._agent.RunStreamAsync(content))

    def _BuildInjectPayload(self, info: WorkflowTaskInfo) -> dict:
        """构建注入 Agent 的结果载荷，包含文件路径引用。"""
        result = info.result or {}
        filePath = result.get("filePath") if isinstance(result, dict) else None
        summary = result.get("content") if isinstance(result, dict) else str(result)

        payload: dict = {
            "workflowId": info.workflowId,
            "name": info.name,
            "status": info.workflow.status.name,
            "result": summary,
        }
        if filePath:
            payload["detailFile"] = filePath
            payload["_hint"] = f"Workflow log saved to {filePath}"
        return payload

    # ---- LRU 淘汰 ----

    def _BumpAccess(self, workflowId: int) -> None:
        """更新 workflow 的最后访问时间。"""
        info = self._taskRegistry.get(workflowId)
        if info is not None:
            info.lastAccessedAt = time.time()

    def _EvictLRU(self) -> None:
        """淘汰最久未访问的 workflow，优先淘汰已完成的。"""
        if not self._taskRegistry:
            return

        # 优先从已完成/取消/失败的 workflow 中选 LRU
        doneStatuses = (
            EWorkflowStatus.COMPLETED,
            EWorkflowStatus.FAILED,
            EWorkflowStatus.CANCELLED,
        )
        doneRegistry = {
            wid: info
            for wid, info in self._taskRegistry.items()
            if info.workflow.status in doneStatuses
        }
        source = doneRegistry if doneRegistry else self._taskRegistry
        lruId = min(source, key=lambda wid: source[wid].lastAccessedAt)
        self._RemoveWorkflow(lruId)

    def _RemoveWorkflow(self, workflowId: int) -> None:
        """卸载指定 workflow，取消任务并清理关联资源。"""
        info = self._taskRegistry.pop(workflowId, None)
        if info is None:
            return
        if info.task is not None and not info.task.done():
            info.task.cancel()
        if info.cancellationToken is not None:
            info.cancellationToken.Cancel()
        self._eventLogs.pop(workflowId, None)
        if workflowId in self._pendingInjects:
            self._pendingInjects.remove(workflowId)

    # ---- 辅助 ----

    def _IsAgentRunning(self) -> bool:
        """判断 Agent 当前是否处于 ReAct 循环中。"""
        dataComp = self._agent.GetComponent(DataComponent)
        return dataComp.state != EAgentState.FINISHED