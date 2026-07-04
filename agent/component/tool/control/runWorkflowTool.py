"""Run Workflow tool —— submit a Workflow JSON for background execution."""

from __future__ import annotations

import json as _json
from dataclasses import asdict

from ..baseTool import BaseTool
from ..eToolCategory import EToolCategory
from ..toolResult import ToolResult
from ..toolComponent import ToolComponent


@ToolComponent.Register
class RunWorkflowTool(BaseTool):
    """Submit a Workflow JSON for background execution, return workflowId immediately.

    The workflow runs asynchronously. Use listWorkflows to check status.
    When complete, the result is automatically injected into the Agent's session.
    """

    name: str = "runWorkflow"
    description: str = "Submit workflow JSON for background execution, returns workflowId immediately — result auto-delivers when done, avoid checking status unless necessary"
    category: EToolCategory = EToolCategory.WORKFLOW
    timeout: float = 10.0
    parameters: dict = {
        "type": "object",
        "properties": {
            "json": {
                "type": "string",
                "description": (
                    "Workflow JSON per get_workflow_schema format: {name, nodes: [{id, type, config?}], edges: [{from, to, edgeType?}]}"
                ),
            },
        },
        "required": ["json"],
    }

    async def _InvokeAsync(self, json: str) -> ToolResult:
        """Parse and launch workflow in background, return immediately.

        Args:
            json: Workflow definition as JSON string.

        Returns:
            ToolResult with workflowId and initial status.
        """
        from agent.component.workflow.workflowComponent import WorkflowComponent

        wfComp = self._agent.GetComponent(WorkflowComponent)
        try:
            result = wfComp.Launch(json)
        except Exception as exc:
            return ToolResult.Fail(
                f"Failed to launch workflow: {exc}",
                toolName=self.name,
            )

        return ToolResult.Ok(
            content=_json.dumps(asdict(result), ensure_ascii=False),
            data=result,
            toolName=self.name,
        )
