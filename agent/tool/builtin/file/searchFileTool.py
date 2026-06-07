"""文件搜索工具 —— 通过 glob 模式查找文件。"""

from __future__ import annotations

import os
from pathlib import Path

from ...abstractTool import AbstractTool
from ...eToolCategory import EToolCategory
from ...toolResult import ToolResult
from ...toolRegistry import G_ToolRegistry

MAX_RESULTS = 2000


@G_ToolRegistry.Register
class SearchFileTool(AbstractTool):
    """通过 glob 模式搜索文件。

    支持通配符匹配，返回匹配的文件路径列表。
    """

    name: str = "search_file"
    description: str = (
        "Search for files matching a glob pattern. "
        "Returns a list of matching file paths. "
        "Use this to find specific files by name pattern, e.g. '*.py', 'test_*.ts'."
    )
    category: EToolCategory = EToolCategory.FILE
    parameters: dict = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "The glob pattern to match, e.g. '*.py' or '**/test_*.ts'",
            },
            "rootDir": {
                "type": "string",
                "description": "Optional. The root directory to search in (defaults to current working directory)",
            },
        },
        "required": ["pattern"],
    }

    def _invoke(self, pattern: str, rootDir: str = ".") -> ToolResult:
        try:
            rootPath = Path(rootDir).resolve()
            if not rootPath.is_dir():
                return ToolResult.Fail(f"Not a directory: {rootDir}", toolName=self.name)

            # 使用 pathlib 的 rglob，原生支持 ** 递归匹配
            matches = list(rootPath.rglob(pattern))

            # 去重并保持顺序
            seen: set[str] = set()
            results: list[str] = []
            for p in matches:
                if p.is_file():
                    rel = str(p.relative_to(rootPath)).replace("\\", "/")
                    if rel not in seen:
                        seen.add(rel)
                        results.append(rel)
                    if len(results) >= MAX_RESULTS:
                        break

            if not results:
                return ToolResult.Ok(
                    f"No files matching '{pattern}' found in '{rootDir}'.",
                    toolName=self.name,
                )

            content = f"[Files matching '{pattern}' in '{rootDir}' ({len(results)} results)]\n"
            content += "\n".join(f"  {r}" for r in results)
            if len(results) >= MAX_RESULTS:
                content += f"\n... (truncated at {MAX_RESULTS} results)"

            return ToolResult.Ok(content, toolName=self.name)

        except Exception as exc:
            return ToolResult.Fail(f"Search failed: {exc}", toolName=self.name)
