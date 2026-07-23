"""File 搜索工具共享模块 —— rg 检测、目录剪枝、.mangoIgnore 解析。

仅供同包内 globTool / grepTool 引用，不通过 __init__.py 对外暴露。
实例由 ToolComponent 创建并注入到 File 类工具。
"""

from __future__ import annotations

import fnmatch
import os
import shutil
from typing import Callable


_IgnorePattern = tuple[str, bool, bool]  # (pattern, isNegated, isDirOnly)


class FileSearchUtils:
    """File 搜索工具实例 —— rg 检测、目录剪枝、.mangoIgnore 过滤。

    mangoIgnorePath 由 ToolComponent 在 OnInitialize 中从 Settings 读取后注入，
    本类不依赖 Settings 模块。
    """

    # ---- 常量 ----

    PRUNE_DIRS: frozenset[str] = frozenset({"node_modules", "__pycache__", ".git"})

    # ---- ripgrep 缓存（类级，跨实例共享） ----

    _rgPath: str | None = None
    _rgChecked: bool = False

    # ---- 实例初始化 ----

    def __init__(self, mangoIgnorePath: str = "") -> None:
        self._mangoIgnorePath = mangoIgnorePath
        self._patterns: list[_IgnorePattern] | None = None
        self._filter: Callable[[str], bool | None] | None = None

    # ==================== ripgrep ====================

    @classmethod
    def DetectRg(cls) -> str | None:
        """检测 ripgrep 可用性，进程级缓存，避免重复扫描 PATH。"""
        if not cls._rgChecked:
            cls._rgPath = shutil.which("rg")
            cls._rgChecked = True
        return cls._rgPath

    # ==================== 目录剪枝 ====================

    @staticmethod
    def PruneWalkDirs(subDirs: list[str]) -> None:
        """原地剪枝 os.walk 的 subDirs 列表，跳过隐藏目录与重型依赖目录。"""
        subDirs[:] = [d for d in subDirs if not d.startswith(".") and d not in FileSearchUtils.PRUNE_DIRS]

    # ==================== .mangoIgnore ====================

    def GetIgnoreFilter(self) -> Callable[[str], bool | None]:
        """获取 .mangoIgnore 过滤器（惰性加载，实例级缓存）。

        Returns:
            (relPath: str) -> 是否忽略：
                True   — 命中忽略模式
                False  — 命中 ! 否定模式（不忽略）
                None   — 未命中任何模式
        """
        if not self._mangoIgnorePath:
            return lambda relPath: None

        if self._filter is not None:
            return self._filter

        self._patterns = self._ParseIgnoreFile(self._mangoIgnorePath)
        self._filter = self._BuildIgnoreMatcher(self._patterns)
        return self._filter

    def AppendIgnoreFileArg(self, cmd: list[str]) -> None:
        """若 .mangoIgnore 文件存在，向 rg 命令追加 --ignore-file 参数。"""
        if self._mangoIgnorePath and os.path.isfile(self._mangoIgnorePath):
            cmd.extend(["--ignore-file", self._mangoIgnorePath])

    # ==================== 内部解析 ====================

    @staticmethod
    def _ParseIgnoreFile(filePath: str) -> list[_IgnorePattern]:
        """解析 gitignore 风格文件，返回 [(pattern, isNegated, isDirOnly), ...] 列表。

        规则：
        - 跳过空行与 # 注释行
        - ! 开头表示否定（包含）模式
        - 末尾 / 表示仅匹配目录（不剥离，保留 isDirOnly 标记传递到匹配器）
        """
        patterns: list[_IgnorePattern] = []
        if not filePath or not os.path.isfile(filePath):
            return patterns

        with open(filePath, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.rstrip("\n\r").rstrip()
                if not line or line.startswith("#"):
                    continue

                isNegated = False
                if line.startswith("!"):
                    isNegated = True
                    line = line[1:]

                isDirOnly = line.endswith("/")
                if isDirOnly:
                    line = line[:-1]

                if line:
                    patterns.append((line, isNegated, isDirOnly))

        return patterns

    @staticmethod
    def _BuildIgnoreMatcher(patterns: list[_IgnorePattern]) -> Callable[[str], bool | None]:
        """将解析后的 pattern 列表构建为匹配函数。

        匹配语义（对齐 gitignore 核心规则）：
        - 含 / 的模式：从根锚定匹配完整相对路径
        - 不含 / 的模式：仅匹配 basename（任意层级）
        - 目录专属模式（/ 结尾）：匹配路径中任意目录组件
        - 否定模式返回 False（不忽略），普通模式返回 True（忽略）
        - 后出现的模式覆盖先出现的
        """
        if not patterns:
            return lambda relPath: None

        def _Matcher(relPath: str) -> bool | None:
            normalized = relPath.replace("\\", "/")

            result = None
            for pat, isNegated, isDirOnly in patterns:
                if isDirOnly:
                    # 目录专属：检查路径中是否有目录组件匹配该 pattern
                    for component in normalized.split("/"):
                        if fnmatch.fnmatch(component, pat):
                            result = not isNegated
                            break
                elif "/" in pat:
                    if fnmatch.fnmatch(normalized, pat):
                        result = not isNegated
                else:
                    basename = normalized.rsplit("/", 1)[-1] if "/" in normalized else normalized
                    if fnmatch.fnmatch(basename, pat):
                        result = not isNegated
            return result

        return _Matcher
