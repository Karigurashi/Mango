"""Glob 工具 —— 按 glob 模式搜索文件。

优先使用 ripgrep（rg --files）加速：原生支持 .gitignore、.mangoIgnore、并行目录遍历、
跳过隐藏目录（.git/node_modules 等），大仓库下比 pathlib.rglob 快 1-2 个数量级。
rg 不可用时回退到带目录剪枝的 os.walk（仍优于无剪枝的 rglob）。
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path, PurePath

from ..baseTool import BaseTool
from ..eToolCategory import EToolCategory
from ..toolResult import ToolResult
from ..toolComponent import ToolComponent
from agent.component.contex.eContextLodLevel import EContextLodLevel
from .fileUtils import FileSearchUtils

MAX_RESULTS = 2000


@ToolComponent.Register
class SearchFileTool(BaseTool):
    """按 glob 模式搜索文件，只返回匹配文件的路径。限制最多 2000 个结果。

    支持通配符匹配，返回匹配的文件路径列表。
    """

    name: str = "glob"
    description: str = "Search files by glob pattern. Returns matching paths. Limited to 2000 results"
    category: EToolCategory = EToolCategory.FILE
    timeout: float = 15.0
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

    @property
    def _fileUtils(self) -> FileSearchUtils:
        """从 ToolComponent 获取 FileSearchUtils 实例。"""
        return self._agent.GetComponent(ToolComponent).fileSearchUtils

    def _Invoke(self, query: str, path: str = ".") -> ToolResult:
        try:
            rootPath = Path(path)
            if not rootPath.is_dir():
                return ToolResult.Fail(f"Not a directory: {path}", toolName=self.name)

            if FileSearchUtils.DetectRg():
                result = self._InvokeWithRipgrep(query, rootPath)
                if result is not None:
                    return result

            return self._InvokeWithWalk(query, rootPath)

        except Exception as exc:
            return ToolResult.Fail(f"Search failed: {exc}", toolName=self.name)

    def _InvokeWithRipgrep(self, query: str, rootPath: Path) -> ToolResult | None:
        """rg --files + glob 过滤 + .mangoIgnore，返回 None 表示需回退。

        rglob 语义对齐：无斜杠模式匹配任意层级 basename（rg 的 gitignore 语义天然一致）；
        含斜杠且未以 **/ 开头的模式补 **/ 前缀（rg 中含斜杠模式默认锚定根目录）。
        """
        rgPattern = query if query.startswith("**/") or "/" not in query else f"**/{query}"
        globFlag = "--iglob" if os.name == "nt" else "-g"

        cmd: list[str] = ["rg", "--no-config", "--files", globFlag, rgPattern]
        self._fileUtils.AppendIgnoreFileArg(cmd)
        cmd.append(str(rootPath))

        try:
            # 子进程超时与工具 timeout（15s）对齐
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=15,
                encoding="utf-8", errors="replace",
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return None
        if proc.returncode == 2:
            return None

        rootStr = str(rootPath)
        results: list[str] = []
        seen: set[str] = set()
        for line in proc.stdout.splitlines():
            filePath = line.strip()
            if not filePath:
                continue
            rel = os.path.relpath(filePath, rootStr).replace("\\", "/")
            if rel not in seen:
                seen.add(rel)
                results.append(rel)
            if len(results) >= MAX_RESULTS:
                break

        return self._BuildResult(query, rootStr, results)

    def _InvokeWithWalk(self, query: str, rootPath: Path) -> ToolResult:
        """os.walk 回退实现，剪枝隐藏目录、重型依赖目录与 .mangoIgnore 规则。"""
        matchPattern = query[3:] if query.startswith("**/") else query
        rootStr = str(rootPath)
        ignoreFilter = self._fileUtils.GetIgnoreFilter()
        results: list[str] = []

        for dirRoot, subDirs, files in os.walk(rootPath):
            FileSearchUtils.PruneWalkDirs(subDirs)
            for filename in files:
                rel = os.path.relpath(os.path.join(dirRoot, filename), rootStr).replace("\\", "/")
                if ignoreFilter(rel) is True:
                    continue
                if PurePath(rel).match(matchPattern):
                    results.append(rel)
                    if len(results) >= MAX_RESULTS:
                        break
            if len(results) >= MAX_RESULTS:
                break

        return self._BuildResult(query, rootStr, results)

    def _BuildResult(self, query: str, rootStr: str, results: list[str]) -> ToolResult:
        if not results:
            return ToolResult.Ok(
                f"No files matching '{query}' found in '{rootStr}'.",
                toolName=self.name,
            )

        content = f"[Files matching '{query}' in '{rootStr}' ({len(results)} results)]\n"
        content += "\n".join(f"  {r}" for r in results)
        if len(results) >= MAX_RESULTS:
            content += f"\n... (truncated at {MAX_RESULTS} results)"
        return ToolResult.Ok(content, toolName=self.name)
