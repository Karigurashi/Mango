"""内容外存 —— LOD 3 大内容的落盘存储与路径引用。"""

from __future__ import annotations

import hashlib
import os
import time


class ContentStore:
    """LOD 3 内容的外部文件存储。

    当工具返回大结果时（行数/字节数超过阈值），原始内容写入外部文件，
    上下文中仅保留路径引用 + 摘要，AI 需要时可调用 read 工具按路径重新加载。

    Attributes:
        storeDir: 外存根目录（默认 ".contex/store"）。
        maxFileSize: 单文件最大字节数（超限会截断）。
    """

    def __init__(self, storeDir: str = ".contex/store", maxFileSize: int = 10 * 1024 * 1024) -> None:
        self.storeDir = storeDir
        self.maxFileSize = maxFileSize
        self._fileIndex: dict[str, str] = {}

    def Store(self, content: str, metadata: dict | None = None) -> str:
        """将大内容写入外存，返回文件路径。

        Args:
            content: 原始内容字符串。
            metadata: 可选元数据（调用方、时间戳等）。

        Returns:
            相对于 storeDir 的文件路径。
        """
        os.makedirs(self.storeDir, exist_ok=True)

        contentHash = hashlib.md5(content.encode("utf-8")).hexdigest()[:12]
        timestamp = int(time.time() * 1000)
        filename = f"{timestamp}_{contentHash}.txt"
        filepath = os.path.join(self.storeDir, filename)

        truncated = content[: self.maxFileSize]
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(truncated)

        self._fileIndex[contentHash] = filepath
        return filepath

    def Load(self, path: str) -> str | None:
        """按路径加载外存内容。

        Args:
            path: 相对于 storeDir 的文件路径。

        Returns:
            文件内容，路径无效或文件不存在时返回 None。
        """
        fullPath = os.path.join(self.storeDir, os.path.basename(path)) if not os.path.isabs(path) else path
        try:
            with open(fullPath, "r", encoding="utf-8") as f:
                return f.read()
        except (FileNotFoundError, OSError):
            return None

    def GetSummary(self, path: str, maxChars: int = 200) -> str:
        """获取外存内容的前 N 个字符作为摘要。

        Args:
            path: 相对于 storeDir 的文件路径。
            maxChars: 摘要最大字符数。

        Returns:
            摘要字符串。
        """
        content = self.Load(path)
        if content is None:
            return f"[内容不可用: {path}]"
        if len(content) <= maxChars:
            return content
        return content[:maxChars] + "..."

    def Cleanup(self, olderThan: float | None = None) -> int:
        """清理过期外存文件。

        Args:
            olderThan: 清理此时间（Unix 时间戳）之前的文件，None 表示全部清理。

        Returns:
            清理的文件数量。
        """
        if not os.path.isdir(self.storeDir):
            return 0

        count = 0
        for filename in os.listdir(self.storeDir):
            filepath = os.path.join(self.storeDir, filename)
            if not os.path.isfile(filepath):
                continue
            if olderThan is not None:
                mtime = os.path.getmtime(filepath)
                if mtime >= olderThan:
                    continue
            try:
                os.remove(filepath)
                count += 1
            except OSError:
                pass

        return count

    def BuildPathReference(self, path: str, originalSize: int, summary: str) -> str:
        """生成 LOD 3 路径引用文案。

        Args:
            path: 外存文件路径。
            originalSize: 原始内容大小（字节/行数）。
            summary: 内容摘要。

        Returns:
            注入上下文引用的文本。
        """
        return (
            f"[工具结果已存储至 {path} ({self._FormatSize(originalSize)})]\n"
            f"摘要: {summary}\n"
            f"(需要完整内容时请使用 read 工具读取 {path})"
        )

    @staticmethod
    def _FormatSize(size: int) -> str:
        """格式化大小显示。"""
        if size >= 1024 * 1024:
            return f"{size / (1024 * 1024):.1f}MB"
        if size >= 1024:
            return f"{size / 1024:.1f}KB"
        return f"{size}B"

    def __repr__(self) -> str:
        return f"ContentStore(dir={self.storeDir!r}, files={len(self._fileIndex)})"
