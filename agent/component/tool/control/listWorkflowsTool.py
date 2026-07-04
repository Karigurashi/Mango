"""List Workflows tool —— return status of all background workflows."""

from __future__ import annotations

import json as _json

from ..baseTool import BaseTool
from ..eToolCategory import EToolCategory
from ..toolResult import ToolResult
from ..toolComponent import ToolComponent


@ToolComponent.Register
class ListWorkflowsTool(BaseTool):
    """List all background workflows with their current status.

    Returns running, completed, failed, and cancelled workflows.
    Completed workflows include their per-node results.
    """

    name: str = "listWorkflows"
    description: str = "List background workflows and status (RUNNING/COMPLETED/FAILED/CANCELLED)"
    category: EToolCategory = EToolCategory.WORKFLOW
    parameters: dict = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    def _Invoke(self) -> ToolResult:
        """Return all workflow statuses.

        Returns:
            ToolResult with JSON list of workflow info dicts.
        """
        from agent.component.workflow.workflowComponent import WorkflowComponent

        wfComp = self._agent.GetComponent(WorkflowComponent)
        workflows = wfComp.ListWorkflows()
        return ToolResult.Ok(
            content=_json.dumps(workflows, ensure_ascii=False, indent=2),
            data=workflows,
            toolName=self.name,
        )
