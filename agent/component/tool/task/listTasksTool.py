"""List Tasks tool —— list Agent-owned tasks, optionally filtered by type."""

from __future__ import annotations

import json as _json
import time

from ..baseTool import BaseTool
from ..eToolCategory import EToolCategory
from ..toolResult import ToolResult
from ..toolComponent import ToolComponent


@ToolComponent.Register
class ListTasksTool(BaseTool):
    """List background tasks with status and results.

    Optional taskType filters by SCHEDULED / WORKFLOW.
    Omit taskType to list all tasks owned by this Agent.
    """

    name: str = "listTasks"
    description: str = (
        "List tasks for this Agent. Optional taskType: SCHEDULED | WORKFLOW; "
        "omit to list all."
    )
    category: EToolCategory = EToolCategory.TASK
    parameters: dict = {
        "type": "object",
        "properties": {
            "taskType": {
                "type": "string",
                "enum": ["SCHEDULED", "WORKFLOW"],
                "description": "Filter by task type; omit to list all",
            },
        },
        "required": [],
    }

    _lastCallTime: float = 0.0
    _RATE_LIMIT_SECONDS: float = 3.0

    def _Invoke(self, taskType: str | None = None) -> ToolResult:
        """Return task statuses with optional type filter and rate-limit protection."""
        now = time.time()
        elapsed = now - self._lastCallTime
        if elapsed < self._RATE_LIMIT_SECONDS:
            return ToolResult.Fail(
                f"Rate limit: last call was {elapsed:.1f}s ago. "
                f"Minimum interval is {self._RATE_LIMIT_SECONDS}s.",
                toolName=self.name,
            )
        self._lastCallTime = now

        from agent.component.schedule.scheduleComponent import ScheduleComponent
        from agent.component.workflow.workflowComponent import WorkflowComponent
        from task.schedule import ScheduleTask, TaskSpec
        from task.workflow.workflow import Workflow

        filterType: str | None = None
        if taskType:
            key = taskType.strip().upper()
            if key not in ("SCHEDULED", "WORKFLOW"):
                return ToolResult.Fail(
                    f"Unknown taskType '{taskType}'. Use SCHEDULED or WORKFLOW.",
                    toolName=self.name,
                )
            filterType = key

        scheduleComp = self._agent.GetComponent(ScheduleComponent)
        workflowComp = self._agent.GetComponent(WorkflowComponent)
        tasks = []
        if filterType in (None, "WORKFLOW"):
            tasks.extend(workflowComp.ListTasks())
        if filterType in (None, "SCHEDULED"):
            tasks.extend(scheduleComp.ListTasks())

        items: list[dict] = []
        for task in tasks:
            info = task.info
            item: dict = {
                "taskId": info.taskId,
                "name": info.name,
                "taskType": self._GetTaskTypeName(task),
                "status": info.status.name,
                "createdAt": int(info.createdAt),
            }
            if isinstance(task, ScheduleTask) and task.taskSpec.specId:
                item["specId"] = task.taskSpec.specId
                item["expression"] = task.taskSpec.expression
                item["isRecurring"] = True
                item["fireCount"] = task.taskSpec.fireCount
                item["prompt"] = task.taskSpec.prompt
                if task.taskSpec.lastFiredAt:
                    item["lastFiredAt"] = int(task.taskSpec.lastFiredAt)
            if isinstance(task, Workflow):
                item["workflowId"] = info.taskId
            if info.error:
                item["error"] = info.error
            payload = workflowComp.GetTaskResult(info.taskId) if isinstance(task, Workflow) else None
            if payload is not None:
                if isinstance(payload, TaskSpec):
                    item["specId"] = payload.specId
                    item["prompt"] = payload.prompt
                elif isinstance(payload, dict):
                    if payload.get("result"):
                        item["result"] = payload["result"]
                    if payload.get("error"):
                        item["error"] = payload["error"]
                    if payload.get("prompt"):
                        item["prompt"] = payload["prompt"]
                    if payload.get("detailFile"):
                        item["detailFile"] = payload["detailFile"]
                else:
                    item["result"] = payload
            items.append(item)

        return ToolResult.Ok(
            content=_json.dumps(items, ensure_ascii=False, indent=2),
            data=items,
            toolName=self.name,
        )

    @staticmethod
    def _GetTaskTypeName(task: object) -> str:
        from task.schedule import ScheduleTask
        from task.workflow.workflow import Workflow

        if isinstance(task, ScheduleTask):
            return "SCHEDULED"
        if isinstance(task, Workflow):
            return "WORKFLOW"
        return "GENERIC"
