"""文件读取工具 —— 读取指定路径的文件内容。"""

from __future__ import annotations

import os

from ..baseTool import BaseTool
from ..eToolCategory import EToolCategory
from ..toolResult import ToolResult
from ..toolComponent import ToolComponent

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


@ToolComponent.Register
class ReadFileTool(BaseTool):
    """读取文件内容并返回文本。

    支持文本文件的读取，自动处理编码问题。
    """

    name: str = "read_file"
    description: str = (
        "Read the contents of a file at the given path. "
        "Returns the file content as text. "
        "Use this to inspect source code, configuration files, or any text-based file."
    )
    category: EToolCategory = EToolCategory.FILE
    skipPersist: bool = True
    parameters: dict = {
        "type": "object",
        "properties": {
            "filePath": {
                "type": "string",
                "description": "The absolute or relative path to the file to read",
            },
            "startLine": {
                "type": "integer",
                "description": "Optional. The 1-based line number to start reading from",
            },
            "endLine": {
                "type": "integer",
                "description": "Optional. The 1-based line number to end reading at (inclusive)",
            },
        },
        "required": ["filePath"],
    }

    def _Invoke(
        self,
        filePath: str,
        startLine: int = 0,
        endLine: int = 0,
    ) -> ToolResult:
        try:
            try:
                safePath = self._SanitizePath(filePath, self._GetAllowedRoot())
            except ValueError as exc:
                return ToolResult.Fail(str(exc), toolName=self.name)

            if not os.path.isfile(safePath):
                return ToolResult.Fail(f"File not found: {filePath}", toolName=self.name)

            fileSize = os.path.getsize(safePath)
            if fileSize > MAX_FILE_SIZE:
                return ToolResult.Fail(
                    f"File too large: {fileSize} bytes exceeds limit of {MAX_FILE_SIZE} bytes ({filePath}).",
                    toolName=self.name,
                )

            with open(safePath, "r", encoding="utf-8", errors="replace") as f:
                if startLine > 0 or endLine > 0:
                    lines = f.readlines()
                    total = len(lines)
                    sl = max(1, startLine) if startLine > 0 else 1
                    el = min(total, endLine) if endLine > 0 else total
                    content = "".join(lines[sl - 1 : el])
                else:
                    content = f.read()

            header = f"[File: {filePath}]\n"
            return ToolResult.Ok(header + content, toolName=self.name)

        except Exception as exc:
            return ToolResult.Fail(f"Failed to read '{filePath}': {exc}", toolName=self.name)
