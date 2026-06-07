"""代码搜索工具 —— 使用正则表达式搜索文件内容。"""

from __future__ import annotations

import os
import re

from ...abstractTool import AbstractTool
from ...eToolCategory import EToolCategory
from ...toolResult import ToolResult
from ...toolRegistry import G_ToolRegistry

MAX_RESULTS = 500
MAX_LINE_LENGTH = 500
CONTEXT_LINES = 2


@G_ToolRegistry.Register
class GrepCodeTool(AbstractTool):
    """使用正则表达式搜索文件内容。

    支持文件类型过滤、上下文行展示。
    """

    name: str = "grep_code"
    description: str = (
        "Search file contents using a regular expression pattern. "
        "Returns matching lines with file paths and line numbers. "
        "Use this to find code patterns, function definitions, imports, or any text content."
    )
    category: EToolCategory = EToolCategory.FILE
    parameters: dict = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "The regular expression pattern to search for",
            },
            "rootDir": {
                "type": "string",
                "description": "Optional. The root directory to search in (defaults to current working directory)",
            },
            "fileTypes": {
                "type": "string",
                "description": "Optional. Comma-separated file extensions to filter, e.g. '.py,.ts,.js'",
            },
            "contextLines": {
                "type": "integer",
                "description": "Optional. Number of context lines to show around each match (default 2)",
            },
            "caseSensitive": {
                "type": "boolean",
                "description": "Optional. Whether the search should be case-sensitive (default false)",
            },
        },
        "required": ["pattern"],
    }

    def _invoke(
        self,
        pattern: str,
        rootDir: str = ".",
        fileTypes: str = "",
        contextLines: int = CONTEXT_LINES,
        caseSensitive: bool = False,
    ) -> ToolResult:
        try:
            rootDir = os.path.abspath(rootDir)
            if not os.path.isdir(rootDir):
                return ToolResult.Fail(f"Not a directory: {rootDir}", toolName=self.name)

            flags = 0 if caseSensitive else re.IGNORECASE
            try:
                regex = re.compile(pattern, flags)
            except re.error as exc:
                return ToolResult.Fail(f"Invalid regex pattern: {exc}", toolName=self.name)

            extSet = None
            if fileTypes:
                extSet = {e.strip() if e.strip().startswith(".") else f".{e.strip()}" for e in fileTypes.split(",")}

            results: list[str] = []
            matchCount = 0

            for root, dirs, files in os.walk(rootDir):
                # 跳过隐藏目录和常见忽略目录
                dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "__pycache__", ".git")]

                for filename in files:
                    if extSet and os.path.splitext(filename)[1] not in extSet:
                        continue
                    if matchCount >= MAX_RESULTS:
                        break

                    filePath = os.path.join(root, filename)
                    relPath = os.path.relpath(filePath, rootDir)

                    try:
                        with open(filePath, "r", encoding="utf-8", errors="replace") as f:
                            lines = f.readlines()
                    except (PermissionError, OSError):
                        continue

                    fileMatches: list[str] = []
                    for i, line in enumerate(lines):
                        if regex.search(line):
                            fileMatches.append((i + 1, line.rstrip("\n\r")))
                            matchCount += 1
                            if matchCount >= MAX_RESULTS:
                                break

                    if fileMatches:
                        results.append(f"\n[{relPath}]")
                        lastShown = -contextLines - 1
                        for lineNum, lineText in fileMatches:
                            if lineNum - lastShown > contextLines + 1:
                                results.append("  ...")
                            start = max(0, lineNum - contextLines - 1)
                            for ctxIdx in range(start, min(len(lines), lineNum + contextLines)):
                                ctxLineNum = ctxIdx + 1
                                if ctxLineNum <= lastShown + contextLines:
                                    continue
                                ctxText = lines[ctxIdx].rstrip("\n\r")
                                marker = ">" if ctxLineNum == lineNum else " "
                                ctxText = ctxText[:MAX_LINE_LENGTH]
                                results.append(f"  {marker} {ctxLineNum:>6}: {ctxText}")
                                lastShown = ctxLineNum

                if matchCount >= MAX_RESULTS:
                    break

            if not results:
                return ToolResult.Ok(
                    f"No matches found for pattern '{pattern}' in '{rootDir}'.",
                    toolName=self.name,
                )

            header = f"[Grep results for '{pattern}' in '{rootDir}' ({matchCount} matches)"
            if extSet:
                header += f", types: {', '.join(sorted(extSet))}"
            header += "]"
            content = header + "\n".join(results)

            return ToolResult.Ok(content, toolName=self.name)

        except Exception as exc:
            return ToolResult.Fail(f"Grep failed: {exc}", toolName=self.name)
