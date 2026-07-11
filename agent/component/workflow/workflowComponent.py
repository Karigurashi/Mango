"""WorkflowComponent —— Agent 侧 workflow 后台任务组件。"""

from __future__ import annotations

import json as _json
from typing import TYPE_CHECKING, Optional

from agent.core.baseComponent import IComponent
from task.core import ETaskStatus
from task.core.taskHandle import TaskHandle
from task.workflow.core.taskProgressData import TaskProgressData
from task.workflow.workflow import Workflow

if TYPE_CHECKING:
    from agent.core.baseAgent import BaseAgent


class WorkflowComponent(IComponent):
    """管理 Workflow 的提交、取消、进度日志和结果查询。"""

    def OnInitialize(self, agent: BaseAgent) -> None:
        self._agent: BaseAgent = agent
        self._eventLogs: dict[int, list[dict]] = {}
        self._handles: dict[int, TaskHandle[Workflow]] = {}
        self._taskResults: dict[int, object] = {}
        self._tasks: dict[int, Workflow] = {}

    def OnDestroy(self) -> None:
        self._eventLogs.clear()
        self._handles.clear()
        self._taskResults.clear()
        self._tasks.clear()

    def AddTask(self, task: Workflow) -> Workflow:
        task.AddProgressListener(lambda data, taskId=task.info.taskId: self._OnWorkflowProgress(taskId, data))
        self._tasks[task.info.taskId] = task
        handle = task.RunAsync(self._OnTaskFinished)
        self._handles[task.info.taskId] = handle
        return task

    def Cancel(self, taskId: int) -> bool:
        if taskId not in self._tasks:
            return False
        handle = self._handles.get(taskId)
        ok = handle.Cancel() if handle is not None else False
        if ok:
            self._handles.pop(taskId, None)
            self._tasks.pop(taskId, None)
            self._eventLogs.pop(taskId, None)
            self._taskResults.pop(taskId, None)
        return ok

    def GetTask(self, taskId: int) -> Optional[Workflow]:
        return self._tasks.get(taskId)

    def GetTaskResult(self, taskId: int) -> object | None:
        return self._taskResults.get(taskId)

    def ListTasks(self) -> list[Workflow]:
        return list(self._tasks.values())

    def _OnTaskFinished(self, handle: TaskHandle) -> None:
        task = self._tasks.get(handle.task.info.taskId)
        if task is None:
            return
        self._HandleWorkflowFinished(task)

    def _OnWorkflowProgress(self, taskId: int, data: TaskProgressData) -> None:
        task = self._tasks.get(taskId)
        if task is None:
            return
        self._AppendProgressLog(taskId, data)

    def _HandleWorkflowFinished(self, task: Workflow) -> None:
        taskId = task.info.taskId

        if task.info.status == ETaskStatus.CANCELLED:
            self._eventLogs.pop(taskId, None)
            self._taskResults.pop(taskId, None)
            return

        if task.info.status != ETaskStatus.COMPLETED:
            return

        payload = self._BuildWorkflowPayload(task)
        self._taskResults[taskId] = payload
        self._eventLogs.pop(taskId, None)

    def _AppendProgressLog(self, taskId: int, data: TaskProgressData) -> None:
        if taskId not in self._eventLogs:
            self._eventLogs[taskId] = []
        self._eventLogs[taskId].append({
            "type": data.kind.name,
            "nodeId": data.nodeId,
            "status": data.status,
            "message": data.message,
        })

    def _BuildWorkflowPayload(self, task: Workflow) -> dict:
        taskId = task.info.taskId
        summary = self._BuildWorkflowSummary(taskId)
        filePath = self._PersistSummary(summary)

        resultContent = ""
        for ev in reversed(self._eventLogs.get(taskId, [])):
            if ev.get("type") == "FLOW_DONE" and ev.get("message"):
                resultContent = ev["message"]
                break
        if not resultContent:
            resultContent = summary[:500]

        payload: dict = {
            "taskId": taskId,
            "workflowId": taskId,
            "name": task.info.name or "Unnamed",
            "status": task.info.status.name,
            "result": resultContent,
        }
        if filePath:
            payload["detailFile"] = filePath
            payload["_hint"] = f"Workflow log saved to {filePath}"
        return payload

    def _BuildWorkflowSummary(self, taskId: int) -> str:
        events = self._eventLogs.get(taskId, [])
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
        from agent.component.store.storeComponent import StoreComponent

        storeComp = self._agent.GetComponent(StoreComponent)
        return storeComp.Store(summary)

    def FormatTaskResult(self, taskId: int) -> str | None:
        result = self._taskResults.get(taskId)
        if result is None:
            return None
        return _json.dumps(result, ensure_ascii=False)
