"""SearchCodebase 工具 —— 语义化代码搜索。

使用关键词 + 正则匹配实现基础语义搜索。
内置文件内容 mtime 缓存，避免重复搜索时全量重读文件。
"""

from __future__ import annotations

import os
from collections import OrderedDict
from typing import Any

from ..baseTool import BaseTool
from ..eToolCategory import EToolCategory
from ..toolResult import ToolResult
from ..toolComponent import ToolComponent
from agent.component.contex.eContextLodLevel import EContextLodLevel

MAX_RESULTS = 200
MAX_READ_BYTES = 51200  # 50KB: 单文件最大读取量
MAX_CACHE_ENTRIES = 500  # 文件缓存上限

_CODE_EXTENSIONS: frozenset[str] = frozenset({
    ".py", ".pyi", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".go", ".rs", ".java", ".kt", ".scala", ".c", ".cpp", ".cc", ".cxx",
    ".h", ".hpp", ".hxx", ".cs", ".rb", ".php", ".swift", ".dart",
    ".lua", ".r", ".sh", ".bash", ".ps1", ".bat",
    ".vue", ".svelte", ".astro",
    ".sql", ".proto", ".thrift",
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
})


@ToolComponent.Register
class SearchCodebaseTool(BaseTool):
    """语义化代码搜索，按含义而非精确文本查找代码。

    内置 mtime 缓存：同一文件未修改时复用上次读取结果，
    避免重复搜索时全量扫描整个仓库。
    """

    _FILE_CACHE: OrderedDict[str, tuple[float, str]] = OrderedDict()

    name: str = "searchCodebase"
    description: str = "Semantic code search by meaning, not exact text. Use for high-level questions."
    category: EToolCategory = EToolCategory.FILE
    resultLodLevel = EContextLodLevel.DISCARDABLE
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Keyword-rich search string"
            },
            "key_words": {
                "type": "string",
                "description": "Top 3 keywords, comma-separated"
            },
            "target_directories": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Directories to narrow search"
            },
        },
        "required": ["query", "key_words"],
    }

    def _Invoke(self, query: str, key_words: str, target_directories: list[str] | None = None) -> ToolResult:
        try:
            keywords = [kw.strip().lower() for kw in key_words.split(",") if kw.strip()]
            if not keywords:
                keywords = [w.lower() for w in query.split() if len(w) > 2]

            dirs = target_directories if target_directories else ["."]
            results: list[str] = []
            matchCount = 0

            for rootDir in dirs:
                if not os.path.isdir(rootDir):
                    continue

                for dirRoot, subDirs, files in os.walk(rootDir):
                    subDirs[:] = [d for d in subDirs if not d.startswith('.') and d not in ("node_modules", "__pycache__", ".git")]

                    for filename in files:
                        ext = os.path.splitext(filename)[1]
                        if ext not in _CODE_EXTENSIONS:
                            continue
                        if matchCount >= MAX_RESULTS:
                            break

                        filePath = os.path.join(dirRoot, filename)

                        try:
                            contentLower = self._GetCachedContent(filePath)
                        except (PermissionError, OSError):
                            continue

                        if all(kw in contentLower for kw in keywords):
                            relPath = os.path.relpath(filePath, rootDir)
                            matchedLines: list[str] = []
                            for i, line in enumerate(contentLower.split("\n"), 1):
                                if any(kw in line for kw in keywords):
                                    matchedLines.append(f"  {i:>6}: {line[:200]}")
                                    if len(matchedLines) >= 5:
                                        break

                            results.append(f"\n[{relPath}]")
                            results.extend(matchedLines)
                            matchCount += 1

                    if matchCount >= MAX_RESULTS:
                        break

            if not results:
                return ToolResult.Ok(
                    f"No files found matching keywords: {key_words}",
                    toolName=self.name,
                )

            header = f"[SearchCodebase results for '{query}' (keywords: {key_words}, {matchCount} files)]"
            return ToolResult.Ok(header + "\n".join(results), toolName=self.name)

        except Exception as exc:
            return ToolResult.Fail(f"SearchCodebase failed: {exc}", toolName=self.name)

    @classmethod
    def _GetCachedContent(cls, filePath: str) -> str:
        """获取文件内容（小写），带 mtime 缓存。

        Raises:
            PermissionError, OSError: 文件读取失败。
        """
        stat = os.stat(filePath)
        mtime = stat.st_mtime

        cached = cls._FILE_CACHE.get(filePath)
        if cached is not None and cached[0] == mtime:
            cls._FILE_CACHE.move_to_end(filePath)
            return cached[1]

        with open(filePath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(MAX_READ_BYTES)
        contentLower = content.lower()

        cls._FILE_CACHE[filePath] = (mtime, contentLower)
        if len(cls._FILE_CACHE) > MAX_CACHE_ENTRIES:
            cls._FILE_CACHE.popitem(last=False)

        return contentLower
