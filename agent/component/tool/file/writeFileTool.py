"""文件写入工具 —— 创建或覆盖文件内容。"""

from __future__ import annotations

import os

from ..baseTool import BaseTool
from ..eToolCategory import EToolCategory
from ..toolResult import ToolResult
from ..tool import ToolComponent


@ToolComponent.Register
class WriteFileTool(BaseTool):
    """将文本内容写入指定路径的文件。

    会自动创建父目录，已存在文件将被覆盖。
    """

    name: str = "write_file"
    description: str = (
        "Write text content to a file at the given path. "
        "Creates parent directories if they don't exist. "
        "Overwrites the file if it already exists. "
        "Use this to create or update source files, configuration, or any text-based file."
    )
    category: EToolCategory = EToolCategory.FILE
    parameters: dict = {
        "type": "object",
        "properties": {
            "filePath": {
                "type": "string",
                "description": "The absolute or relative path to the file to write",
            },
            "content": {
                "type": "string",
                "description": "The text content to write to the file",
            },
        },
        "required": ["filePath", "content"],
    }

    def _Invoke(self, filePath: str, content: str) -> ToolResult:
        try:
            parentDir = os.path.dirname(filePath)
            if parentDir:
                os.makedirs(parentDir, exist_ok=True)

            with open(filePath, "w", encoding="utf-8") as f:
                f.write(content)

            lineCount = content.count("\n") + 1 if content else 0
            return ToolResult.Ok(
                f"Successfully wrote {len(content)} bytes ({lineCount} lines) to '{filePath}'.",
                toolName=self.name,
            )

        except Exception as exc:
            return ToolResult.Fail(f"Failed to write '{filePath}': {exc}", toolName=self.name)
