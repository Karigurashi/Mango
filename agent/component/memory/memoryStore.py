"""记忆文件存储层 —— 纯文件 I/O，管理 workspace/memory/ 目录下的 Markdown 文件。

职责：
- 目录结构初始化（sessions/, memory/, checkpoints/）
- Markdown 文件读写（含 YAML frontmatter 解析）
- 路径拼接与文件存在性检查

不依赖 LLM，不依赖 Memory 抽象。
"""

from __future__ import annotations

import os
import re
import time
from typing import Optional

from common.const import ERoad
from common.logger import Logger

# frontmatter 正则：匹配开头 ---\n...\n---
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


class MemoryStore:
    """Markdown 文件 I/O 核心，封装目录结构和文件操作。

    目录结构::

        {workspace/memory/}/
            sessions/               # 不可变会话摘要
                {sessionId}.md
            memory/                 # LLM 编译的持久记忆
                INDEX.md            # 导航索引
                LOG.md              # 追加式操作日志
                preferences/        # 用户偏好
                decisions/          # 架构决策
                patterns/           # 反馈模式
                references/         # 外部引用
            checkpoints/            # 工作流断点存档
    """

    MAX_SESSIONS = 15
    PRUNE_COUNT = 5

    def __init__(self, baseDir: str | None = None) -> None:
        self._baseDir = baseDir or str(ERoad.MEMORY_DIR)
        self._InitDirs()

    # ---- 属性 ----

    @property
    def BaseDir(self) -> str:
        """记忆根目录。"""
        return self._baseDir

    @property
    def SessionsDir(self) -> str:
        return os.path.join(self._baseDir, "sessions")

    @property
    def MemoryDir(self) -> str:
        return os.path.join(self._baseDir, "memory")

    @property
    def CheckpointsDir(self) -> str:
        return os.path.join(self._baseDir, "checkpoints")

    # ---- 目录初始化 ----

    def _InitDirs(self) -> None:
        """确保所有子目录存在。"""
        dirs = [
            self.SessionsDir,
            self.MemoryDir,
            os.path.join(self.MemoryDir, "preferences"),
            os.path.join(self.MemoryDir, "decisions"),
            os.path.join(self.MemoryDir, "patterns"),
            os.path.join(self.MemoryDir, "references"),
            self.CheckpointsDir,
        ]
        for d in dirs:
            os.makedirs(d, exist_ok=True)

    # ---- 通用 Markdown 读写 ----

    @staticmethod
    def ParseFrontmatter(raw: str) -> tuple[dict[str, str], str]:
        """解析 YAML frontmatter，返回 (元数据字典, 正文)。

        元数据值均为字符串，调用方自行转换类型。
        """
        m = _FRONTMATTER_RE.match(raw)
        if not m:
            return {}, raw.strip()
        body = raw[m.end():].strip()
        meta = {}
        for line in m.group(1).split("\n"):
            line = line.strip()
            if not line or ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                meta[key] = value
        return meta, body

    @staticmethod
    def BuildFrontmatter(meta: dict[str, str]) -> str:
        """根据元数据字典生成 YAML frontmatter 字符串。"""
        if not meta:
            return ""
        lines = ["---"]
        for key, value in meta.items():
            lines.append(f'{key}: "{value}"')
        lines.append("---")
        return "\n".join(lines) + "\n"

    def ReadFile(self, filePath: str) -> str | None:
        """读取文件全部内容，不存在时返回 None。"""
        if not os.path.isfile(filePath):
            return None
        try:
            with open(filePath, "r", encoding="utf-8") as f:
                return f.read()
        except OSError as e:
            Logger.Error(f"MemoryStore.ReadFile failed: {filePath} | {e}")
            return None

    def WriteFile(self, filePath: str, content: str) -> bool:
        """写入文件，自动创建父目录。返回是否成功。"""
        try:
            os.makedirs(os.path.dirname(filePath), exist_ok=True)
            with open(filePath, "w", encoding="utf-8") as f:
                f.write(content)
            return True
        except OSError as e:
            Logger.Error(f"MemoryStore.WriteFile failed: {filePath} | {e}")
            return False

    def AppendFile(self, filePath: str, content: str) -> bool:
        """追加写入文件，返回是否成功。"""
        try:
            os.makedirs(os.path.dirname(filePath), exist_ok=True)
            with open(filePath, "a", encoding="utf-8") as f:
                f.write(content)
            return True
        except OSError as e:
            Logger.Error(f"MemoryStore.AppendFile failed: {filePath} | {e}")
            return False

    def FileExists(self, filePath: str) -> bool:
        return os.path.isfile(filePath)

    def ListFiles(self, directory: str, extension: str = ".md") -> list[str]:
        """列出目录下所有指定扩展名的文件（仅文件名，不含路径）。"""
        if not os.path.isdir(directory):
            return []
        try:
            return sorted(
                f for f in os.listdir(directory)
                if f.endswith(extension) and os.path.isfile(os.path.join(directory, f))
            )
        except OSError:
            return []

    # ---- Session 读写 ----

    def SaveSession(self, sessionId: str, content: str) -> bool:
        """保存会话摘要到 sessions/{sessionId}.md，写入后自动裁剪超出上限的旧会话。"""
        path = os.path.join(self.SessionsDir, f"{sessionId}.md")
        ok = self.WriteFile(path, content)
        if ok:
            self._PruneSessions(self.MAX_SESSIONS, self.PRUNE_COUNT)
        return ok

    def LoadSession(self, sessionId: str) -> str | None:
        """读取指定会话摘要。"""
        path = os.path.join(self.SessionsDir, f"{sessionId}.md")
        return self.ReadFile(path)

    def ListSessions(self) -> list[str]:
        """列出所有已保存的会话 ID（无扩展名）。"""
        files = self.ListFiles(self.SessionsDir, ".md")
        return [f[:-3] for f in files]

    # ---- 记忆页面读写 ----

    def MemoryPagePath(self, categoryDir: str, pageName: str) -> str:
        """构造记忆页面完整路径。

        Args:
            categoryDir: 分类子目录名（preferences/decisions/patterns/references）。
            pageName: 页面文件名（不含扩展名）。
        """
        return os.path.join(self.MemoryDir, categoryDir, f"{pageName}.md")

    def SaveMemoryPage(self, categoryDir: str, pageName: str, content: str) -> bool:
        """保存记忆页面。"""
        path = self.MemoryPagePath(categoryDir, pageName)
        return self.WriteFile(path, content)

    def LoadMemoryPage(self, categoryDir: str, pageName: str) -> str | None:
        """加载记忆页面。"""
        path = self.MemoryPagePath(categoryDir, pageName)
        return self.ReadFile(path)

    def ListMemoryPages(self, categoryDir: str) -> list[str]:
        """列出某分类下所有记忆页面文件名（无扩展名）。"""
        dirPath = os.path.join(self.MemoryDir, categoryDir)
        files = self.ListFiles(dirPath, ".md")
        return [f[:-3] for f in files]

    def DeleteMemoryPage(self, categoryDir: str, pageName: str) -> bool:
        """删除记忆页面。"""
        path = self.MemoryPagePath(categoryDir, pageName)
        try:
            if os.path.isfile(path):
                os.remove(path)
                return True
            return False
        except OSError:
            return False

    # ---- 会话裁剪 ----

    def _PruneSessions(self, maxCount: int, pruneCount: int) -> int:
        """会话数量超出 maxCount 时，按文件修改时间删除最旧的 pruneCount 条。

        Args:
            maxCount: 允许的最大会话文件数。
            pruneCount: 超出后删除的条数。

        Returns:
            实际删除的文件数。
        """
        files = self.ListFiles(self.SessionsDir, ".md")
        if len(files) <= maxCount:
            return 0

        # 按文件修改时间升序（最旧在前）
        filesWithMtime: list[tuple[str, float]] = []
        for f in files:
            fpath = os.path.join(self.SessionsDir, f)
            try:
                filesWithMtime.append((f, os.path.getmtime(fpath)))
            except OSError:
                filesWithMtime.append((f, 0.0))
        filesWithMtime.sort(key=lambda x: x[1])

        # 删除最旧的 pruneCount 条
        removed = 0
        for f, _ in filesWithMtime[:pruneCount]:
            fpath = os.path.join(self.SessionsDir, f)
            try:
                os.remove(fpath)
                removed += 1
                Logger.Info(f"MemoryStore: pruned old session {f[:-3][:8]}...")
            except OSError as e:
                Logger.Warning(f"MemoryStore: failed to prune {f}: {e}")

        if removed > 0:
            self.AppendLog(f"Pruned {removed} old session(s), remaining {len(files) - removed}")

        return removed

    # ---- LOG.md ----

    @property
    def LogPath(self) -> str:
        return os.path.join(self.MemoryDir, "LOG.md")

    def AppendLog(self, entry: str) -> bool:
        """追加一行操作日志。"""
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")
        line = f"- [{timestamp}] {entry}\n"
        return self.AppendFile(self.LogPath, line)

    def ReadLog(self) -> str | None:
        return self.ReadFile(self.LogPath)

    # ---- INDEX.md ----

    @property
    def IndexPath(self) -> str:
        return os.path.join(self.MemoryDir, "INDEX.md")

    # ---- 表示 ----

    def __repr__(self) -> str:
        return f"MemoryStore(baseDir={self._baseDir!r})"
