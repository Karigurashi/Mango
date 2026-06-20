"""内容外存 —— LOD 3 大内容的落盘存储与路径引用。"""

from __future__ import annotations

import hashlib
import os
import tempfile
import time


class ContentStore:
    """LOD 3 内容的外部文件存储。

    当工具返回大结果时（行数/字节数超过阈值），原始内容写入外部文件，
    上下文中仅保留路径引用 + 摘要，AI 需要时可调用 read 工具按路径重新加载。

    Attributes:
        storeDir: 外存根目录（默认 ".contex/store"）。
        maxFileSize: 单文件最大字节数（超限会截断）。
    """

    def __init__(self, storeDir: str = ".contex/store", maxFileSize: int = 0, maxTotalSize: int = 0) -> None:
        self.storeDir = storeDir
        self.maxFileSize = maxFileSize  # 0 时使用内部默认值 10MB
        self.maxTotalSize = maxTotalSize  # 0 时使用内部默认值 500MB
        # 总容量缓存：避免每次 _EvictIfNeeded/GetTotalSize 都全目录扫描，
        # Store/Cleanup 等修改路径会置 _cacheDirty=True，下一次 GetTotalSize 重算。
        self._cachedSize: int = 0
        self._cacheDirty: bool = True

    def Store(self, content: str) -> str:
        """将大内容原子写入外存，返回文件路径。

        采用 tmpfile + os.replace 保证并发安全：
        - 先写入临时文件，再原子 rename 到目标路径
        - 避免多个协程写入同一文件时出现内容截断或竞态

        写入前检查总容量，超限时先淘汰最旧文件腾出空间。

        Args:
            content: 原始内容字符串。

        Returns:
            相对于 storeDir 的文件路径。
        """
        os.makedirs(self.storeDir, exist_ok=True)

        # 总容量守卫：超限时淘汰最旧文件
        self._EvictIfNeeded(len(content.encode("utf-8")))

        contentHash = hashlib.md5(content.encode("utf-8")).hexdigest()[:12]
        timestamp = int(time.time() * 1000)
        filename = f"{timestamp}_{contentHash}.txt"
        filepath = os.path.join(self.storeDir, filename)

        truncated = content[: (self.maxFileSize or 10 * 1024 * 1024)]
        # 原子写入：先写临时文件，再 os.replace
        fd, tmpPath = tempfile.mkstemp(dir=self.storeDir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(truncated)
            os.replace(tmpPath, filepath)
        except Exception:
            # 清理临时文件，避免磁盘泄漏
            if os.path.exists(tmpPath):
                os.unlink(tmpPath)
            raise

        # 写入成功后标记缓存失效
        self._cacheDirty = True
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

        if count > 0:
            self._cacheDirty = True
        return count

    def GetTotalSize(self) -> int:
        """计算外存目录中所有文件的总字节数。

        引入脏标位缓存：仅在 Store/Cleanup/_EvictIfNeeded 等修改路径后
        触发重新扫描，否则直接返回上次结果，避免高频写入场景下的 O(N) 全扫。
        """
        if not self._cacheDirty:
            return self._cachedSize
        if not os.path.isdir(self.storeDir):
            self._cachedSize = 0
            self._cacheDirty = False
            return 0
        totalSize = 0
        for filename in os.listdir(self.storeDir):
            filepath = os.path.join(self.storeDir, filename)
            if os.path.isfile(filepath):
                try:
                    totalSize += os.path.getsize(filepath)
                except OSError:
                    pass
        self._cachedSize = totalSize
        self._cacheDirty = False
        return totalSize

    def _EvictIfNeeded(self, incomingSize: int) -> int:
        """总容量超限时按最旧优先淘汰文件，为即将写入的内容腾出空间。

        Args:
            incomingSize: 即将写入的内容字节数。

        Returns:
            淘汰的文件数量。
        """
        if (self.maxTotalSize or 500 * 1024 * 1024) <= 0:
            return 0

        currentSize = self.GetTotalSize()
        if currentSize + incomingSize <= (self.maxTotalSize or 500 * 1024 * 1024):
            return 0

        # 收集所有文件及其 mtime，按最旧优先排序
        if not os.path.isdir(self.storeDir):
            return 0

        fileEntries = []
        for filename in os.listdir(self.storeDir):
            filepath = os.path.join(self.storeDir, filename)
            if not os.path.isfile(filepath):
                continue
            try:
                mtime = os.path.getmtime(filepath)
                size = os.path.getsize(filepath)
                fileEntries.append((mtime, filepath, size))
            except OSError:
                continue

        fileEntries.sort(key=lambda e: e[0])  # 按最旧优先

        evicted = 0
        freedSize = 0
        targetFree = (currentSize + incomingSize) - (self.maxTotalSize or 500 * 1024 * 1024)
        for _, filepath, size in fileEntries:
            if freedSize >= targetFree:
                break
            try:
                os.remove(filepath)
                freedSize += size
                evicted += 1
            except OSError:
                pass

        if evicted > 0:
            self._cacheDirty = True
        return evicted

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

    def BuildPersistedPreview(
        self, path: str, content: str, previewChars: int = 500
    ) -> str:
        """生成大结果落盘后的预览文本，参照 Claude Code <persisted-output> 标签。

        Args:
            path: 外存文件路径。
            content: 原始完整内容。
            previewChars: 预览截断字符数。

        Returns:
            注入上下文的预览文本。
        """
        charCount = len(content)
        preview = content[:previewChars]
        truncated = charCount > previewChars

        lines = [
            f"<persisted-output file=\"{path}\">",
            f"Size: {charCount} chars | Stored: {path}",
        ]
        if truncated:
            lines.append("--- preview (first chars) ---")
            lines.append(preview)
            lines.append(f"... ({charCount - previewChars} more chars)")
        else:
            lines.append(content)
        lines.append("Use read_file tool to read the full content if needed.")
        lines.append("</persisted-output>")

        return "\n".join(lines)

    @staticmethod
    def _FormatSize(size: int) -> str:
        """格式化大小显示。"""
        if size >= 1024 * 1024:
            return f"{size / (1024 * 1024):.1f}MB"
        if size >= 1024:
            return f"{size / 1024:.1f}KB"
        return f"{size}B"

    def __repr__(self) -> str:
        return f"ContentStore(dir={self.storeDir!r})"
