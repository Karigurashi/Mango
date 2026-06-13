"""记忆健康检查 —— Karpathy LLM Wiki 的"Lint"操作。

对标代码 ESLint，对记忆系统执行规则化健康检查：
- 孤页检测：INDEX.md 中无入链的页面
- 死链检测：INDEX.md 引用了不存在的页面
- 过期检测：超过 N 天未更新的低置信度页面
- 矛盾检测：LLM 驱动的页面间矛盾扫描（可选，需 LLMClient）
"""

from __future__ import annotations

import os
import re
import time
from typing import Optional, TYPE_CHECKING

from common.logger import Logger
from .eMemoryCategory import EMemoryCategory
from llm.llmRequestParams import LLMRequestParams
from llm.provider.chatMessage import ChatMessage

if TYPE_CHECKING:
    from .memoryStore import MemoryStore
    from .memoryIndex import MemoryIndex


class LintReport:
    """健康检查报告。"""

    def __init__(self) -> None:
        self.orphanPages: list[str] = []
        self.deadLinks: list[str] = []
        self.stalePages: list[str] = []
        self.lowConfidencePages: list[str] = []
        self.contradictions: list[str] = []
        self.suggestions: list[str] = []

    @property
    def IssueCount(self) -> int:
        return (
            len(self.orphanPages)
            + len(self.deadLinks)
            + len(self.stalePages)
            + len(self.lowConfidencePages)
            + len(self.contradictions)
        )

    def ToMarkdown(self) -> str:
        """生成 Markdown 格式报告。"""
        lines = [
            f"# Memory Lint Report",
            f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Total Issues: {self.IssueCount}",
            "",
        ]

        sections = [
            ("## Orphan Pages (no incoming links)", self.orphanPages),
            ("## Dead Links (INDEX.md references missing pages)", self.deadLinks),
            ("## Stale Pages (not updated in 30+ days)", self.stalePages),
            ("## Low Confidence Pages", self.lowConfidencePages),
            ("## Potential Contradictions", self.contradictions),
            ("## Suggestions", self.suggestions),
        ]
        for header, items in sections:
            if items:
                lines.append(header)
                for item in items:
                    lines.append(f"- {item}")
                lines.append("")

        return "\n".join(lines)

    def __repr__(self) -> str:
        return f"LintReport(issues={self.IssueCount})"


class MemoryLint:
    """记忆健康检查器。

    使用方式::

        store = MemoryStore()
        index = MemoryIndex(store)
        lint = MemoryLint(store, index)
        report = lint.Run()
        print(report.ToMarkdown())
    """

    # 过期阈值（天）
    STALE_DAYS = 30

    def __init__(
        self,
        store: "MemoryStore",
        index: "MemoryIndex",
        llmClient: object | None = None,
    ) -> None:
        self._store = store
        self._index = index
        self._llmClient = llmClient

    def Run(self) -> LintReport:
        """执行全部健康检查（同步，不调 LLM）。

        LLM 驱动的矛盾检测需单独调用 DetectContradictionsAsync。
        """
        report = LintReport()
        self._CheckOrphans(report)
        self._CheckDeadLinks(report)
        self._CheckStale(report)
        self._CheckLowConfidence(report)
        return report

    async def RunAsync(self) -> LintReport:
        """执行全部健康检查（含 LLM 矛盾检测）。"""
        report = self.Run()
        if self._llmClient is not None:
            await self._DetectContradictionsAsync(report)
        return report

    # ---- 规则检查 ----

    def _CheckOrphans(self, report: LintReport) -> None:
        """检测孤页：INDEX.md 中有记录但未被任何页面引用的页面。"""
        entries = self._index.GetAll()
        if not entries:
            return

        # 收集所有被引用的页面名（扫描所有 memory 页面的 [[wikilinks]]）
        referenced: set[str] = set()
        linkRe = re.compile(r"\[\[(.+?)\]\]")

        for pageName in entries:
            for catDir in ("preferences", "decisions", "patterns", "references"):
                content = self._store.LoadMemoryPage(catDir, pageName)
                if content:
                    for match in linkRe.finditer(content):
                        referenced.add(match.group(1))

        for pageName in entries:
            if pageName not in referenced and pageName != "INDEX":
                report.orphanPages.append(
                    f"[[{pageName}]] — no other memory page links to it"
                )

    def _CheckDeadLinks(self, report: LintReport) -> None:
        """检测 INDEX.md 中引用了但文件不存在的页面。"""
        entries = self._index.GetAll()
        for pageName, (cat, _desc) in entries.items():
            if not self._store.FileExists(
                self._store.MemoryPagePath(cat.DirName, pageName)
            ):
                report.deadLinks.append(
                    f"[[{pageName}]] ({cat.DirName}) — file missing on disk"
                )

    def _CheckStale(self, report: LintReport) -> None:
        """检测过期页面：超过 STALE_DAYS 天未更新。"""
        entries = self._index.GetAll()
        now = time.time()
        threshold = self.STALE_DAYS * 86400

        for pageName, (cat, _desc) in entries.items():
            path = self._store.MemoryPagePath(cat.DirName, pageName)
            try:
                mtime = os.path.getmtime(path)
                ageDays = (now - mtime) / 86400
                if ageDays > self.STALE_DAYS:
                    report.stalePages.append(
                        f"[[{pageName}]] ({cat.DirName}) — last updated {ageDays:.0f} days ago"
                    )
            except OSError:
                pass

    def _CheckLowConfidence(self, report: LintReport) -> None:
        """检测低置信度页面。"""
        entries = self._index.GetAll()
        for pageName, (cat, _desc) in entries.items():
            content = self._store.LoadMemoryPage(cat.DirName, pageName)
            if content is None:
                continue
            meta, _body = self._store.ParseFrontmatter(content)
            if meta.get("confidence", "").lower() == "low":
                report.lowConfidencePages.append(
                    f"[[{pageName}]] ({cat.DirName}) — confidence=low"
                )

    async def _DetectContradictionsAsync(self, report: LintReport) -> None:
        """LLM 驱动的页面间矛盾检测。"""
        entries = self._index.GetAll()
        if len(entries) < 2 or self._llmClient is None:
            return

        # 只检查同分类页面之间的矛盾
        pagesByCat: dict[EMemoryCategory, list[str]] = {}
        for pageName, (cat, _desc) in entries.items():
            pagesByCat.setdefault(cat, []).append(pageName)

        for cat, pageNames in pagesByCat.items():
            if len(pageNames) < 2:
                continue
            # 加载前 5 个页面内容进行矛盾检测
            contents = []
            for pn in pageNames[:5]:
                c = self._store.LoadMemoryPage(cat.DirName, pn)
                if c:
                    contents.append(f"### [[{pn}]]\n{c[:1500]}")
            if len(contents) < 2:
                continue

            prompt = (
                "Check the following memory pages for contradictions. "
                "If two pages make conflicting claims, list them.\n\n"
                + "\n\n".join(contents)
                + "\n\nList any contradictions, or reply 'NONE'."
            )

            try:
                response = await self._llmClient.InvokeAsync(
                    messages=[ChatMessage.User(prompt)],
                    requestParams=LLMRequestParams(temperature=0.0, maxTokens=1024),
                )
                result = response.content.strip()
                if result and result.upper() != "NONE":
                    report.contradictions.append(f"[{cat.DirName}] {result}")
            except Exception as e:
                Logger.Warning(f"MemoryLint: contradiction detection failed: {e}")

    def __repr__(self) -> str:
        return f"MemoryLint(entries={self._index.EntryCount})"
