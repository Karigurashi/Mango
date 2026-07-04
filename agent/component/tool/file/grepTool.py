"""Grep 工具 —— 高性能文件内容搜索。

优先使用 ripgrep（rg）子进程加速（原生支持 .gitignore、并行搜索、mmap），
rg 不可用时回退到 Python re 引擎。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections import OrderedDict, deque
from itertools import islice
from typing import Any

from ..baseTool import BaseTool
from ..eToolCategory import EToolCategory
from ..toolResult import ToolResult
from ..toolComponent import ToolComponent
from agent.component.contex.eContextLodLevel import EContextLodLevel

MAX_RESULTS = 500
MAX_LINE_LENGTH = 500
CONTEXT_LINES = 2
MAX_REGEX_CACHE_SIZE = 128

_RG_MATCH_SEP = ":"
_RG_CONTEXT_SEP = "-"


@ToolComponent.Register
class GrepCodeTool(BaseTool):
    """高性能文件内容搜索，支持正则表达式。结果自动展开为完整语法块。

    优先使用 ripgrep 子进程（10-100x 加速），回退 Python re 引擎。
    """

    _REGEX_CACHE: OrderedDict[tuple[str, int], re.Pattern] = OrderedDict()

    @classmethod
    def _CompileRegex(cls, pattern: str, flags: int) -> re.Pattern:
        """编译正则表达式，带 LRU 缓存。"""
        cacheKey = (pattern, flags)
        cached = cls._REGEX_CACHE.get(cacheKey)
        if cached is not None:
            cls._REGEX_CACHE.move_to_end(cacheKey)
            return cached

        compiled = re.compile(pattern, flags)
        cls._REGEX_CACHE[cacheKey] = compiled
        if len(cls._REGEX_CACHE) > MAX_REGEX_CACHE_SIZE:
            cls._REGEX_CACHE.popitem(last=False)
        return compiled

    name: str = "grep"
    description: str = "Search file contents by regex. Auto-expands to syntax blocks."
    category: EToolCategory = EToolCategory.FILE
    resultLodLevel = EContextLodLevel.DISCARDABLE
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "regex": {
                "type": "string",
                "description": "Regex pattern"
            },
            "path": {
                "type": "string",
                "description": "Target file or directory"
            },
            "type": {
                "type": "string",
                "description": "File type filter, e.g. js, py, rust"
            },
            "glob": {
                "type": "string",
                "description": "File glob filter"
            },
            "caseInsensitive": {
                "type": "boolean",
                "description": "Case-insensitive"
            },
            "contextAfter": {
                "type": "number",
                "description": "Lines after match"
            },
            "contextBefore": {
                "type": "number",
                "description": "Lines before match"
            },
            "contextAround": {
                "type": "number",
                "description": "Lines before and after match"
            },
            "multiline": {
                "type": "boolean",
                "description": "Multiline matching"
            },
        },
        "required": ["regex"],
    }

    def _Invoke(
        self,
        regex: str,
        path: str = ".",
        type: str = "",
        glob: str = "",
        caseInsensitive: bool = False,
        contextAfter: int = 0,
        contextBefore: int = 0,
        contextAround: int = 0,
        multiline: bool = False,
    ) -> ToolResult:
        if contextAround:
            if not contextBefore:
                contextBefore = contextAround
            if not contextAfter:
                contextAfter = contextAround
        if not contextBefore and not contextAfter:
            contextBefore = CONTEXT_LINES
            contextAfter = CONTEXT_LINES

        searchPath = path
        try:
            if not os.path.exists(searchPath):
                return ToolResult.Fail(f"Path not found: {searchPath}", toolName=self.name)

            if os.path.isfile(searchPath):
                return self._InvokeOnSingleFile(
                    regex, searchPath,
                    caseInsensitive, contextAfter, contextBefore, multiline,
                )

            if not os.path.isdir(searchPath):
                return ToolResult.Fail(f"Not a file or directory: {searchPath}", toolName=self.name)

            if shutil.which("rg"):
                result = self._InvokeWithRipgrep(
                    regex, searchPath, type, glob,
                    caseInsensitive, contextAfter, contextBefore, multiline,
                )
                if result is not None:
                    return result

            return self._InvokeWithPythonRe(
                regex, searchPath, type, glob,
                caseInsensitive, contextAfter, contextBefore, multiline,
            )

        except Exception as exc:
            return ToolResult.Fail(f"Grep failed: {exc}", toolName=self.name)

    def _InvokeWithRipgrep(
        self,
        regex: str,
        rootDir: str,
        fileType: str,
        globPattern: str,
        caseInsensitive: bool,
        contextAfter: int,
        contextBefore: int,
        multiline: bool,
    ) -> ToolResult | None:
        """使用 ripgrep 子进程搜索，返回 None 表示需回退。"""
        cmd: list[str] = ["rg", "--no-config", "-n", "--color", "never"]

        if contextBefore > 0:
            cmd.extend(["-B", str(contextBefore)])
        if contextAfter > 0:
            cmd.extend(["-A", str(contextAfter)])
        if caseInsensitive:
            cmd.append("-i")
        if multiline:
            cmd.append("-U")

        if fileType:
            for ft in fileType.split(","):
                ft = ft.strip()
                if ft:
                    cmd.extend(["-t", ft])

        if globPattern:
            cmd.extend(["-g", globPattern])

        cmd.extend(["--max-count", str(MAX_RESULTS)])
        cmd.extend([regex, rootDir])

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                encoding="utf-8",
                errors="replace",
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return None

        if proc.returncode == 2:
            return None

        if not proc.stdout.strip():
            return ToolResult.Ok(
                f"No matches found for regex '{regex}' in '{rootDir}'.",
                toolName=self.name,
            )

        return self._ParseRipgrepOutput(regex, rootDir, proc.stdout, fileType)

    @staticmethod
    def _ParseRipgrepOutput(
        regex: str,
        rootDir: str,
        output: str,
        fileType: str,
    ) -> ToolResult:
        """解析 rg 标准文本输出为格式化结果。"""
        results: list[str] = []
        matchCount = 0
        currentRelPath = ""
        fileResults: list[str] = []

        for line in output.splitlines():
            if not line:
                continue

            match = re.match(r"^(.+?)([-:])(\d+)([-:])(.*)$", line)
            if match:
                filePath = match.group(1)
                lineNum = int(match.group(3))
                isMatch = match.group(4) == _RG_MATCH_SEP
                content = match.group(5)

                relPath = os.path.relpath(filePath, rootDir)
                if relPath != currentRelPath:
                    if fileResults:
                        results.extend(fileResults)
                        fileResults.clear()
                    currentRelPath = relPath
                    fileResults.append(f"\n[{relPath}]")

                marker = ">" if isMatch else " "
                truncated = content[:MAX_LINE_LENGTH]
                fileResults.append(f"  {marker} {lineNum:>6}: {truncated}")
                if isMatch:
                    matchCount += 1
            else:
                fileResults.append(f"  {line[:MAX_LINE_LENGTH]}")

        if fileResults:
            results.extend(fileResults)

        if not results:
            return ToolResult.Ok(
                f"No matches found for regex '{regex}' in '{rootDir}'.",
                toolName=self.name,
            )

        header = f"[Grep results for '{regex}' in '{rootDir}' ({matchCount} matches"
        if fileType:
            header += f", types: {fileType}"
        header += "]"

        return ToolResult.Ok(header + "\n".join(results), toolName=self.name)

    def _InvokeOnSingleFile(
        self,
        regex: str,
        filePath: str,
        caseInsensitive: bool,
        contextAfter: int,
        contextBefore: int,
        multiline: bool,
    ) -> ToolResult:
        """对单个文件执行 grep，优先 rg，回退 Python re。"""
        if shutil.which("rg"):
            cmd: list[str] = ["rg", "--no-config", "-n", "--color", "never"]
            if contextBefore > 0:
                cmd.extend(["-B", str(contextBefore)])
            if contextAfter > 0:
                cmd.extend(["-A", str(contextAfter)])
            if caseInsensitive:
                cmd.append("-i")
            if multiline:
                cmd.append("-U")
            cmd.extend(["--max-count", str(MAX_RESULTS)])
            cmd.extend([regex, filePath])

            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    encoding="utf-8",
                    errors="replace",
                )
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                pass
            else:
                if proc.returncode != 2:
                    if not proc.stdout.strip():
                        return ToolResult.Ok(
                            f"No matches found for regex '{regex}' in '{filePath}'.",
                            toolName=self.name,
                        )
                    return self._ParseRipgrepOutput(regex, os.path.dirname(filePath) or ".", proc.stdout, "")

        return self._InvokePythonReOnFile(
            regex, filePath, caseInsensitive, contextAfter, contextBefore, multiline,
        )

    def _InvokePythonReOnFile(
        self,
        regex: str,
        filePath: str,
        caseInsensitive: bool,
        contextAfter: int,
        contextBefore: int,
        multiline: bool,
    ) -> ToolResult:
        """Python re 引擎对单文件执行 grep。"""
        flags = re.IGNORECASE if caseInsensitive else 0
        if multiline:
            flags |= re.DOTALL
        try:
            compiledRegex = self._CompileRegex(regex, flags)
        except re.error as exc:
            return ToolResult.Fail(f"Invalid regex pattern: {exc}", toolName=self.name)

        fileMatches: list[tuple[int, str]] = []
        contextRing: deque[tuple[int, str]] = deque(maxlen=contextBefore + 1)
        pendingTrailing = 0
        captured: dict[int, str] = {}
        matchCount = 0

        try:
            with open(filePath, "r", encoding="utf-8", errors="replace") as f:
                for idx, line in enumerate(f, start=1):
                    stripped = line.rstrip("\n\r")
                    contextRing.append((idx, stripped))

                    if compiledRegex.search(line):
                        fileMatches.append((idx, stripped))
                        matchCount += 1
                        for ctxIdx, ctxText in contextRing:
                            captured.setdefault(ctxIdx, ctxText)
                        pendingTrailing = contextAfter
                        if matchCount >= MAX_RESULTS:
                            break
                        continue

                    if pendingTrailing > 0:
                        captured.setdefault(idx, stripped)
                        pendingTrailing -= 1
        except (PermissionError, OSError) as exc:
            return ToolResult.Fail(f"Cannot read file: {exc}", toolName=self.name)

        if not fileMatches:
            return ToolResult.Ok(
                f"No matches found for regex '{regex}' in '{filePath}'.",
                toolName=self.name,
            )

        relPath = os.path.basename(filePath)
        results: list[str] = [f"\n[{relPath}]"]
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

        header = f"[Grep results for '{regex}' in '{filePath}' ({matchCount} matches)]"
        return ToolResult.Ok(header + "\n".join(results), toolName=self.name)

    def _InvokeWithPythonRe(
        self,
        regex: str,
        rootDir: str,
        fileType: str,
        globPattern: str,
        caseInsensitive: bool,
        contextAfter: int,
        contextBefore: int,
        multiline: bool,
    ) -> ToolResult:
        """Python re 引擎回退实现。"""
        flags = re.IGNORECASE if caseInsensitive else 0
        if multiline:
            flags |= re.DOTALL
        try:
            compiledRegex = self._CompileRegex(regex, flags)
        except re.error as exc:
            return ToolResult.Fail(f"Invalid regex pattern: {exc}", toolName=self.name)

        extSet = None
        if fileType:
            extSet = {e.strip() if e.strip().startswith(".") else f".{e.strip()}" for e in fileType.split(",")}

        globFilter = None
        if globPattern:
            import fnmatch
            globFilter = lambda name: fnmatch.fnmatch(name, globPattern)  # noqa: E731

        results: list[str] = []
        matchCount = 0

        for dirRoot, subDirs, files in os.walk(rootDir):
            subDirs[:] = [d for d in subDirs if not d.startswith('.') and d not in ("node_modules", "__pycache__", ".git")]

            for filename in files:
                if extSet and os.path.splitext(filename)[1] not in extSet:
                    continue
                if globFilter and not globFilter(filename):
                    continue
                if matchCount >= MAX_RESULTS:
                    break

                filePath = os.path.join(dirRoot, filename)
                relPath = os.path.relpath(filePath, rootDir)

                fileMatches: list[tuple[int, str]] = []
                contextRing: deque[tuple[int, str]] = deque(maxlen=contextBefore + 1)
                pendingTrailing = 0
                captured: dict[int, str] = {}

                try:
                    with open(filePath, "r", encoding="utf-8", errors="replace") as f:
                        for idx, line in enumerate(f, start=1):
                            stripped = line.rstrip("\n\r")
                            contextRing.append((idx, stripped))

                            if compiledRegex.search(line):
                                fileMatches.append((idx, stripped))
                                matchCount += 1
                                for ctxIdx, ctxText in contextRing:
                                    captured.setdefault(ctxIdx, ctxText)
                                pendingTrailing = contextAfter
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
                f"No matches found for regex '{regex}' in '{rootDir}'.",
                toolName=self.name,
            )

        header = f"[Grep results for '{regex}' in '{rootDir}' ({matchCount} matches)"
        if extSet:
            header += f", types: {', '.join(sorted(extSet))}"
        header += "]"

        return ToolResult.Ok(header + "\n".join(results), toolName=self.name)
