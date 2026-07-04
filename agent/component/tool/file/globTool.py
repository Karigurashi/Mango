"""Glob 工具 —— 按 glob 模式搜索文件。"""

from __future__ import annotations

import os
from pathlib import Path

from ..baseTool import BaseTool
from ..eToolCategory import EToolCategory
from ..toolResult import ToolResult
from ..toolComponent import ToolComponent
from agent.component.contex.eContextLodLevel import EContextLodLevel

MAX_RESULTS = 2000


@ToolComponent.Register
class SearchFileTool(BaseTool):
    """按 glob 模式搜索文件，只返回匹配文件的路径。限制最多 2000 个结果。

    支持通配符匹配，返回匹配的文件路径列表。
    """

    name: str = "glob"
    description: str = "Search files by glob pattern. Returns matching paths. Limited to 2000 results"
    category: EToolCategory = EToolCategory.FILE
    resultLodLevel = EContextLodLevel.DISCARDABLE
    parameters: dict = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Glob pattern, MUST be relative. e.g. *.go, **/test/*.py",
            },
            "path": {
                "type": "string",
                "description": "Search directory (supports absolute paths). Defaults to workspace root",
            },
        },
        "required": ["query"],
    }

    def _Invoke(self, query: str, path: str = ".") -> ToolResult:
        try:
            rootPath = Path(path)
            if not rootPath.is_dir():
                return ToolResult.Fail(f"Not a directory: {path}", toolName=self.name)

            # 使用 pathlib 的 rglob，原生支持 ** 递归匹配
            matches = list(rootPath.rglob(query))

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
                    f"No files matching '{query}' found in '{path}'.",
                    toolName=self.name,
                )

            content = f"[Files matching '{query}' in '{path}' ({len(results)} results)]\n"
            content += "\n".join(f"  {r}" for r in results)
            if len(results) >= MAX_RESULTS:
                content += f"\n... (truncated at {MAX_RESULTS} results)"

            return ToolResult.Ok(content, toolName=self.name)

        except Exception as exc:
            return ToolResult.Fail(f"Search failed: {exc}", toolName=self.name)
