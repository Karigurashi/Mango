"""Task 工具 —— 定时任务与 Workflow（均为 Task 子系统）。"""

from .createTaskTool import CreateTaskTool
from .deleteTaskTool import DeleteTaskTool
from .runWorkflowTool import RunWorkflowTool
from .getWorkflowSchemaTool import GetWorkflowSchemaTool
from .listTasksTool import ListTasksTool
from .cancelWorkflowTool import CancelWorkflowTool

# enableWorkflow 开关控制的工具名（同属 TASK 分类，需按名启停）
WORKFLOW_TOOL_NAMES: tuple[str, ...] = (
    "runWorkflow",
    "cancelWorkflow",
    "getWorkflowSchema",
)

__all__ = [
    "CreateTaskTool",
    "DeleteTaskTool",
    "RunWorkflowTool",
    "GetWorkflowSchemaTool",
    "ListTasksTool",
    "CancelWorkflowTool",
    "WORKFLOW_TOOL_NAMES",
]
