"""INDEX.md 索引管理器 —— 记忆导航层。

INDEX.md 是 Memory 系统的唯一入口。ContextAssembler 只加载 INDEX.md（< 500 tokens），
然后按需读取具体的 memory/*.md 页面。

INDEX.md 格式::

    # Memory Index

    ## Preferences
    - [[preferences-coding-style]] - Python coding style guide
    - [[preferences-test-convention]] - Testing convention

    ## Decisions
    - [[decisions-redis-cache]] - Redis caching strategy

    ## Patterns
    - [[patterns-avoid-mocks]] - Avoid mocks in DB tests

    ## References
    - [[references-slack-channel]] - Team Slack channel
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .memoryStore import MemoryStore
    from .eMemoryCategory import EMemoryCategory


class MemoryIndex:
    """INDEX.md 读写管理器。

    使用方式::

        store = MemoryStore()
        index = MemoryIndex(store)
        index.Upsert("preferences-coding-style", EMemoryCategory.PREFERENCE, "Python coding style guide")
        blocks = index.ToContextBlocks()  # → ["## Preferences", "- [[preferences-...]]", ...]
    """

    _HEADER = "# Memory Index\n\n"

    def __init__(self, store: "MemoryStore") -> None:
        self._store = store
        self._entries: dict[str, tuple["EMemoryCategory", str]] = {}
        self._Load()

    # ---- 读写 ----

    def Upsert(self, pageName: str, category: "EMemoryCategory", description: str) -> None:
        """添加或更新索引条目。"""
        self._entries[pageName] = (category, description)
        self._Save()

    def Remove(self, pageName: str) -> bool:
        """移除索引条目，返回是否成功。"""
        if pageName not in self._entries:
            return False
        del self._entries[pageName]
        self._Save()
        return True

    def Find(self, pageName: str) -> tuple["EMemoryCategory", str] | None:
        """查找指定页面的分类和描述。"""
        return self._entries.get(pageName)

    def GetAll(self) -> dict[str, tuple["EMemoryCategory", str]]:
        """返回所有条目的浅拷贝。"""
        return dict(self._entries)

    # ---- 持久化 ----

    def _Load(self) -> None:
        """从 INDEX.md 解析现有条目。"""
        from .eMemoryCategory import EMemoryCategory

        raw = self._store.ReadFile(self._store.IndexPath)
        if not raw:
            return

        currentCategory: EMemoryCategory | None = None
        # 匹配 ## CategoryName 标题
        headerRe = re.compile(r"^## (.+)$")
        # 匹配 - [[page-name]] - description
        entryRe = re.compile(r"^- \[\[(.+?)\]\]\s*-\s*(.+)$")

        for line in raw.split("\n"):
            line = line.strip()
            if not line:
                continue

            hm = headerRe.match(line)
            if hm:
                currentCategory = EMemoryCategory.FromDirName(hm.group(1).lower())
                continue

            em = entryRe.match(line)
            if em and currentCategory is not None:
                self._entries[em.group(1)] = (currentCategory, em.group(2).strip())

    def _Save(self) -> None:
        """将内存中的条目序列化回 INDEX.md。

        底层调用 MemoryStore.WriteFile 已使用 tempfile + os.replace 原子写入，
        避免多协程同时 Upsert 时子进程崩溃造成 INDEX 被截断。
        """
        from .eMemoryCategory import EMemoryCategory

        # 按分类分组
        groups: dict[EMemoryCategory, list[tuple[str, str]]] = {}
        for pageName, (cat, desc) in self._entries.items():
            groups.setdefault(cat, []).append((pageName, desc))

        lines = [self._HEADER.rstrip()]
        for cat in (EMemoryCategory.PREFERENCE, EMemoryCategory.DECISION,
                     EMemoryCategory.PATTERN, EMemoryCategory.REFERENCE):
            entries = groups.get(cat, [])
            if not entries:
                continue
            lines.append(f"\n## {cat.DirName.capitalize()}")
            for pageName, desc in sorted(entries):
                lines.append(f"- [[{pageName}]] - {desc}")

        self._store.WriteFile(self._store.IndexPath, "\n".join(lines) + "\n")

    # ---- Context 注入 ----

    def ToContextBlocks(self) -> list[str]:
        """生成供 ContextAssembler 注入 LOD0 的文本块列表。

        Returns:
            按分类组织的文本块，每个分类为一个 block。
        """
        from .eMemoryCategory import EMemoryCategory

        groups: dict[EMemoryCategory, list[str]] = {}
        for pageName, (cat, desc) in sorted(self._entries.items()):
            groups.setdefault(cat, []).append(f"- [[{pageName}]]: {desc}")

        blocks = []
        for cat in (EMemoryCategory.PREFERENCE, EMemoryCategory.DECISION,
                     EMemoryCategory.PATTERN, EMemoryCategory.REFERENCE):
            entries = groups.get(cat)
            if not entries:
                continue
            header = f"## {cat.Label} ({cat.DirName})"
            blocks.append(header + "\n" + "\n".join(entries))

        return blocks

    @property
    def EntryCount(self) -> int:
        return len(self._entries)

    def __repr__(self) -> str:
        return f"MemoryIndex(entries={len(self._entries)})"
