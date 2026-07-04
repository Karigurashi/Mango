"""Cancel Workflow tool —— cancel a running background workflow."""

from __future__ import annotations

import json as _json

from ..baseTool import BaseTool
from ..eToolCategory import EToolCategory
from ..toolResult import ToolResult
from ..toolComponent import ToolComponent


@ToolComponent.Register
class CancelWorkflowTool(BaseTool):
    """Cancel a running background workflow by workflowId.

    Only workflows in "running" status can be cancelled.
    """

    name: str = "cancelWorkflow"
    description: str = "Cancel a running workflow by workflowId"
    category: EToolCategory = EToolCategory.WORKFLOW
    parameters: dict = {
        "type": "object",
        "properties": {
            "workflowId": {
                "type": "integer",
                "description": "Workflow ID to cancel"
            },
        },
        "required": ["workflowId"],
    }

    def _Invoke(self, workflowId: int) -> ToolResult:
        """Cancel the specified workflow.

        Args:
            workflowId: The workflow ID returned by runWorkflow.

        Returns:
            ToolResult indicating success or failure.
        """
        from agent.component.workflow.workflowComponent import WorkflowComponent

        wfComp = self._agent.GetComponent(WorkflowComponent)
        ok = wfComp.Cancel(workflowId)
        if ok:
            return ToolResult.Ok(
                content=_json.dumps({"workflowId": workflowId, "status": "cancelled"}, ensure_ascii=False),
                toolName=self.name,
            )
        return ToolResult.Fail(
            f"Workflow '{workflowId}' not found or not running",
            toolName=self.name,
        )
