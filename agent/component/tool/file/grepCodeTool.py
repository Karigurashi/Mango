"""代码搜索工具 —— 使用正则表达式搜索文件内容。"""

from __future__ import annotations

import os
import re
from collections import deque

from ..baseTool import BaseTool
from ..eToolCategory import EToolCategory
from ..toolResult import ToolResult
from ..toolComponent import ToolComponent

MAX_RESULTS = 500
MAX_LINE_LENGTH = 500
CONTEXT_LINES = 2
MAX_REGEX_CACHE_SIZE = 128


@ToolComponent.Register
class GrepCodeTool(BaseTool):
    """使用正则表达式搜索文件内容。

    支持文件类型过滤、上下文行展示。
    """

    # 类级正则缓存：避免同 pattern 重复编译。
    # key = (pattern, flags) → 已编译的 re.Pattern。
    _REGEX_CACHE: dict[tuple[str, int], re.Pattern] = {}

    @classmethod
    def _CompileRegex(cls, pattern: str, flags: int) -> re.Pattern:
        """编译正则表达式，带过期限制的类级缓存。"""
        cacheKey = (pattern, flags)
        cached = cls._REGEX_CACHE.get(cacheKey)
        if cached is not None:
            return cached

        compiled = re.compile(pattern, flags)

        # 简易 LRU：超过上限时删除首个旧项
        if len(cls._REGEX_CACHE) >= MAX_REGEX_CACHE_SIZE:
            firstKey = next(iter(cls._REGEX_CACHE))
            cls._REGEX_CACHE.pop(firstKey, None)

        cls._REGEX_CACHE[cacheKey] = compiled
        return compiled

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

    def _Invoke(
        self,
        pattern: str,
        rootDir: str = ".",
        fileTypes: str = "",
        contextLines: int = CONTEXT_LINES,
        caseSensitive: bool = False,
    ) -> ToolResult:
        try:
            try:
                rootDir = self._SanitizePath(rootDir, self._GetAllowedRoot())
            except ValueError as exc:
                return ToolResult.Fail(str(exc), toolName=self.name)

            if not os.path.isdir(rootDir):
                return ToolResult.Fail(f"Not a directory: {rootDir}", toolName=self.name)

            flags = 0 if caseSensitive else re.IGNORECASE
            try:
                regex = self._CompileRegex(pattern, flags)
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

                    fileMatches: list[tuple[int, str]] = []
                    contextRing: deque[tuple[int, str]] = deque(maxlen=contextLines + 1)
                    pendingTrailing = 0  # 匹配后需再读取的后置上下文行数
                    capturedTrailing: list[tuple[int, str]] = []
                    captured: dict[int, str] = {}

                    try:
                        with open(filePath, "r", encoding="utf-8", errors="replace") as f:
                            for idx, line in enumerate(f, start=1):
                                stripped = line.rstrip("\n\r")
                                contextRing.append((idx, stripped))

                                if regex.search(line):
                                    fileMatches.append((idx, stripped))
                                    matchCount += 1
                                    # 快照当前环形区（包含当前行及其前 contextLines 行）
                                    for ctxIdx, ctxText in contextRing:
                                        captured.setdefault(ctxIdx, ctxText)
                                    pendingTrailing = contextLines
                                    if matchCount >= MAX_RESULTS:
                                        break
                                    continue

                                if pendingTrailing > 0:
                                    captured.setdefault(idx, stripped)
                                    pendingTrailing -= 1
                    except (PermissionError, OSError):
                        continue

                    if not fileMatches:
                        continue

                    results.append(f"\n[{relPath}]")
                    sortedIdx = sorted(captured.keys())
                    matchSet = {ln for ln, _ in fileMatches}
                    prevIdx = -10
                    for ln in sortedIdx:
                        if ln - prevIdx > 1 and prevIdx > 0:
                            results.append("  ...")
                        ctxText = captured[ln][:MAX_LINE_LENGTH]
                        marker = ">" if ln in matchSet else " "
                        results.append(f"  {marker} {ln:>6}: {ctxText}")
                        prevIdx = ln

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
