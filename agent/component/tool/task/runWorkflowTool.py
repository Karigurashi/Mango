"""Run Workflow tool —— submit a Workflow JSON for background execution."""

from __future__ import annotations

import json as _json

from ..baseTool import BaseTool
from ..eToolCategory import EToolCategory
from ..toolResult import ToolResult
from ..toolComponent import ToolComponent


@ToolComponent.Register
class RunWorkflowTool(BaseTool):
    """Submit a Workflow JSON for background execution, return taskId immediately.

    The workflow runs asynchronously. Use listTasks for status.
    """

    name: str = "runWorkflow"
    description: str = "Submit workflow JSON for background execution; use listTasks for status."
    category: EToolCategory = EToolCategory.TASK
    timeout: float = 10.0
    parameters: dict = {
        "type": "object",
        "properties": {
            "json": {
                "type": "string",
                "description": "Workflow JSON per get_workflow_schema",
            },
        },
        "required": ["json"],
    }

    async def _InvokeAsync(self, json: str) -> ToolResult:
        """Parse Workflow and submit via WorkflowComponent, return immediately.

        Args:
            json: Workflow definition as JSON string.

        Returns:
            ToolResult with taskId and initial status.
        """
        from agent.component.workflow.workflowComponent import WorkflowComponent
        from task.workflow import WorkflowSerializer

        workflowComp = self._agent.GetComponent(WorkflowComponent)
        try:
            wf = WorkflowSerializer.FromJson(json)
            task = workflowComp.AddTask(wf)
        except Exception as exc:
            return ToolResult.Fail(
                f"Failed to launch workflow: {exc}",
                toolName=self.name,
            )

        result = {
            "workflowId": task.info.taskId,
            "status": task.info.status.name,
            "name": task.info.name,
        }
        return ToolResult.Ok(
            content=_json.dumps(result, ensure_ascii=False),
            data=result,
            toolName=self.name,
        )
