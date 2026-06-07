"""目录列表工具 —— 列出目录中的文件和子目录。"""

from __future__ import annotations

import os

from ...abstractTool import AbstractTool
from ...eToolCategory import EToolCategory
from ...toolResult import ToolResult
from ...toolRegistry import G_ToolRegistry


@G_ToolRegistry.Register
class ListDirTool(AbstractTool):
    """列出指定目录的内容。

    返回文件和子目录列表，支持递归展示。
    """

    name: str = "list_dir"
    description: str = (
        "List the contents of a directory. "
        "Returns file and subdirectory names. "
        "Use this to explore project structure, find files, or inspect directories."
    )
    category: EToolCategory = EToolCategory.FILE
    parameters: dict = {
        "type": "object",
        "properties": {
            "dirPath": {
                "type": "string",
                "description": "The absolute path of the directory to list",
            },
            "recursive": {
                "type": "boolean",
                "description": "Optional. If true, list recursively showing the tree structure",
            },
        },
        "required": ["dirPath"],
    }

    def _invoke(self, dirPath: str, recursive: bool = False) -> ToolResult:
        try:
            if not os.path.isdir(dirPath):
                return ToolResult.Fail(f"Not a directory: {dirPath}", toolName=self.name)

            if recursive:
                lines: list[str] = []
                for root, dirs, files in os.walk(dirPath):
                    level = root.replace(dirPath, "").count(os.sep)
                    indent = "  " * level
                    base = os.path.basename(root) or root
                    lines.append(f"{indent}{base}/")
                    for file in files:
                        lines.append(f"{indent}  {file}")
                content = "\n".join(lines)
            else:
                entries = sorted(os.listdir(dirPath))
                lines = []
                for entry in entries:
                    fullPath = os.path.join(dirPath, entry)
                    suffix = "/" if os.path.isdir(fullPath) else ""
                    lines.append(f"  {entry}{suffix}")
                content = f"[Contents of: {dirPath}]\n" + "\n".join(lines)

            if not content.strip():
                content = f"[Directory is empty: {dirPath}]"

            return ToolResult.Ok(content, toolName=self.name)

        except PermissionError:
            return ToolResult.Fail(f"Permission denied: {dirPath}", toolName=self.name)
        except Exception as exc:
            return ToolResult.Fail(f"Failed to list '{dirPath}': {exc}", toolName=self.name)
