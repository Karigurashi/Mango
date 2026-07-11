"""Delete Task tool —— cancel and remove a persisted scheduled task by specId."""

from __future__ import annotations

import json as _json

from ..baseTool import BaseTool
from ..eToolCategory import EToolCategory
from ..toolResult import ToolResult
from ..toolComponent import ToolComponent


@ToolComponent.Register
class DeleteTaskTool(BaseTool):
    """Delete a scheduled task by stable int specId (cancel cron + remove JSON)."""

    name: str = "deleteTask"
    description: str = "Delete a scheduled task by specId returned from createTask"
    category: EToolCategory = EToolCategory.TASK
    parameters: dict = {
        "type": "object",
        "properties": {
            "specId": {
                "type": "integer",
                "description": "Stable integer task specId from createTask",
            },
        },
        "required": ["specId"],
    }

    def _Invoke(self, specId: int) -> ToolResult:
        from agent.component.schedule.scheduleComponent import ScheduleComponent

        scheduleComp = self._agent.GetComponent(ScheduleComponent)
        ok = scheduleComp.DeleteTask(int(specId))
        if not ok:
            return ToolResult.Fail(
                f"Task '{specId}' not found",
                toolName=self.name,
            )

        result = {"specId": int(specId), "deleted": True}
        return ToolResult.Ok(
            content=_json.dumps(result, ensure_ascii=False),
            data=result,
            toolName=self.name,
        )
