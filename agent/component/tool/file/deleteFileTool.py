"""文件删除工具 —— 安全删除指定文件。"""

from __future__ import annotations

import os

from ..baseTool import BaseTool
from ..eToolCategory import EToolCategory
from ..toolResult import ToolResult
from ..toolComponent import ToolComponent


@ToolComponent.Register
class DeleteFileTool(BaseTool):
    """安全删除指定路径的文件。

    仅删除文件，不删除目录。
    """

    name: str = "delete_file"
    description: str = (
        "Delete a file at the given path. "
        "Only deletes files, not directories. "
        "Use this to remove temporary files, generated artifacts, or unwanted files."
    )
    category: EToolCategory = EToolCategory.FILE
    parameters: dict = {
        "type": "object",
        "properties": {
            "filePath": {
                "type": "string",
                "description": "The absolute path of the file to delete",
            },
        },
        "required": ["filePath"],
    }

    def _Invoke(self, filePath: str) -> ToolResult:
        try:
            try:
                safePath = self._SanitizePath(filePath, self._GetAllowedRoot())
            except ValueError as exc:
                return ToolResult.Fail(str(exc), toolName=self.name)

            if not os.path.exists(safePath):
                return ToolResult.Fail(f"File not found: {filePath}", toolName=self.name)

            if os.path.isdir(safePath):
                return ToolResult.Fail(
                    f"Cannot delete directory: {filePath}. Use shell rm -rf for directories.",
                    toolName=self.name,
                )

            os.remove(safePath)
            return ToolResult.Ok(f"Successfully deleted: {filePath}", toolName=self.name)

        except PermissionError:
            return ToolResult.Fail(f"Permission denied: {filePath}", toolName=self.name)
        except Exception as exc:
            return ToolResult.Fail(f"Failed to delete '{filePath}': {exc}", toolName=self.name)
