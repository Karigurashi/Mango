"""Create Task tool —— schedule an AgentWake cron task persisted as JSON."""

from __future__ import annotations

import json as _json

from ..baseTool import BaseTool
from ..eToolCategory import EToolCategory
from ..toolResult import ToolResult
from ..toolComponent import ToolComponent


@ToolComponent.Register
class CreateTaskTool(BaseTool):
    """Create a scheduled Agent-wake task (cron + prompt), persist to tasksDir."""

    name: str = "createTask"
    description: str = (
        "Create a scheduled task that injects a prompt into the Agent at cron time. "
        "Persisted under AgentConfig.tasksDir/schedules.json."
    )
    category: EToolCategory = EToolCategory.TASK
    parameters: dict = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Task display name",
            },
            "expression": {
                "type": "string",
                "description": "5-field cron expression, e.g. '0 9 * * *'",
            },
            "prompt": {
                "type": "string",
                "description": "Instruction injected into Agent when the cron fires",
            },
        },
        "required": ["name", "expression", "prompt"],
    }

    def _Invoke(self, name: str, expression: str, prompt: str) -> ToolResult:
        from agent.component.schedule.scheduleComponent import ScheduleComponent

        if not expression.strip():
            return ToolResult.Fail("expression is required", toolName=self.name)
        if not prompt.strip():
            return ToolResult.Fail("prompt is required", toolName=self.name)

        scheduleComp = self._agent.GetComponent(ScheduleComponent)
        try:
            spec = scheduleComp.CreateScheduleTask(
                name=name.strip(),
                expression=expression.strip(),
                prompt=prompt.strip(),
            )
        except Exception as exc:
            return ToolResult.Fail(
                f"Failed to create task: {exc}",
                toolName=self.name,
            )

        result = {
            "specId": spec.specId,
            "name": spec.name,
            "expression": spec.expression,
            "prompt": spec.prompt,
        }
        return ToolResult.Ok(
            content=_json.dumps(result, ensure_ascii=False),
            data=result,
            toolName=self.name,
        )
