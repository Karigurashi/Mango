"""记忆编译器 —— Karpathy LLM Wiki 的"编译器"概念。

读取 sessions/ 中的不可变会话摘要，调用 LLM 提取关键信息，
编译为结构化的 memory/ 页面并更新 INDEX.md。

核心流程::

    compiler = MemoryCompiler(store, index, llmClient)
    newPages = await compiler.CompileAsync()

编译提示词定义四类记忆的提取规则，LLM 按规则输出 YAML frontmatter + Markdown 正文。
"""

from __future__ import annotations

import time
from typing import Optional, TYPE_CHECKING

from common.cancellationToken import CancellationToken
from common.logger import Logger
from llm.llmRequestParams import LLMRequestParams
from llm.provider.chatMessage import ChatMessage

from .eMemoryCategory import EMemoryCategory

if TYPE_CHECKING:
    from .memoryStore import MemoryStore
    from .memoryIndex import MemoryIndex


_COMPILE_SYSTEM_PROMPT = """You are a memory compiler. Read session summaries and extract structured knowledge into four categories:

1. **PREFERENCE** (偏好): User preferences — coding style, tool choices, naming habits, workflow preferences.
2. **DECISION** (决策): Architecture decisions — technology choices, design trade-offs, migration plans.
3. **PATTERN** (模式): Feedback patterns — correction rules, confirmed good practices, "don't do X" rules with reasons.
4. **REFERENCE** (引用): External references — API docs links, dashboard URLs, contact info, file paths.

For each extracted insight, output a page in this exact format:

---PAGE---
category: preference|decision|pattern|reference
page_name: kebab-case-name
title: Human-readable title
confidence: high|medium|low
sources: session-id-1, session-id-2
---BODY---
Markdown content with **Why** and **How to apply** sections.
---END---

Rules:
- Only extract information useful for future sessions.
- Skip anything derivable from reading code (file paths, project structure).
- Skip debugging solutions (the fix is in the code).
- Skip already-documented content.
- Merge with existing pages if the same topic already exists.
- If nothing worth remembering, output "---NOOP---".
"""


class MemoryCompiler:
    """LLM 驱动的记忆编译器。

    使用方式::

        store = MemoryStore()
        index = MemoryIndex(store)
        compiler = MemoryCompiler(store, index, llmClient)
        newPages = await compiler.CompileAsync()
    """

    def __init__(
        self,
        store: "MemoryStore",
        index: "MemoryIndex",
        llmClient: object | None = None,
    ) -> None:
        """初始化编译器。

        Args:
            store: Markdown 文件存储层。
            index: INDEX.md 管理器。
            llmClient: LLM 客户端实例，用于智能编译。None 时退化为简单摘要提取。
        """
        self._store = store
        self._index = index
        self._llmClient = llmClient

    @property
    def HasLLM(self) -> bool:
        return self._llmClient is not None

    # ---- 公开接口 ----

    async def CompileAsync(
        self,
        sessionIds: list[str] | None = None,
        cancellationToken: Optional[CancellationToken] = None,
    ) -> list[str]:
        """LLM 驱动的记忆编译。

        Args:
            sessionIds: 指定要编译的会话 ID 列表。None 时自动扫描 sessions/ 中的新会话。
            cancellationToken: 取消令牌（可选）。

        Returns:
            新创建或更新的记忆页面名列表。
        """
        if sessionIds is None:
            sessionIds = self._store.ListSessions()

        if not sessionIds:
            Logger.Info("MemoryCompiler: no sessions to compile")
            return []

        # 读取所有会话内容
        sessionsContent = self._LoadSessions(sessionIds)
        if not sessionsContent:
            return []

        # 构建编译提示词
        existingPages = self._BuildExistingPagesContext()

        # 调用 LLM 编译
        if self._llmClient is not None:
            newPages = await self._CompileWithLLMAsync(
                sessionsContent, existingPages, cancellationToken
            )
        else:
            # 无 LLM：简单追加会话摘要为引用记忆
            newPages = self._CompileFallback(sessionsContent)

        # 追加日志
        self._store.AppendLog(
            f"Compiled {len(sessionIds)} session(s) → "
            f"{len(newPages)} page(s): {', '.join(newPages) if newPages else 'none'}"
        )

        return newPages

    async def CompileSingleSessionAsync(
        self,
        sessionId: str,
        cancellationToken: Optional[CancellationToken] = None,
    ) -> list[str]:
        """编译单个会话（便捷方法）。"""
        return await self.CompileAsync([sessionId], cancellationToken)

    # ---- 内部方法 ----

    def _LoadSessions(self, sessionIds: list[str]) -> dict[str, str]:
        """读取所有指定会话内容。

        Returns:
            {sessionId: content} 字典，跳过不存在的会话。
        """
        result = {}
        for sid in sessionIds:
            content = self._store.LoadSession(sid)
            if content:
                result[sid] = content
        return result

    def _BuildExistingPagesContext(self) -> str:
        """构建现有记忆页面的上下文摘要（供 LLM 判断是否需要合并）。"""
        entries = self._index.GetAll()
        if not entries:
            return "(no existing memory pages)"

        lines = ["## Existing Memory Pages"]
        for pageName, (cat, desc) in sorted(entries.items()):
            lines.append(f"- [[{pageName}]] ({cat.DirName}): {desc}")
        return "\n".join(lines)

    async def _CompileWithLLMAsync(
        self,
        sessions: dict[str, str],
        existingContext: str,
        cancellationToken: Optional[CancellationToken],
    ) -> list[str]:
        """使用 LLM 编译会话摘要。"""
        # 构建用户消息
        userParts = [existingContext, "", "## New Sessions to Compile", ""]
        for sid, content in sessions.items():
            # 截断过长的会话内容（保留前 3000 字符）
            truncated = content[:3000]
            if len(content) > 3000:
                truncated += "\n... (truncated)"
            userParts.append(f"### Session: {sid}\n{truncated}\n")

        userMessage = "\n".join(userParts)

        try:
            # 调用 LLMClient（异步非流式），必须传 ChatMessage 对象而非 dict
            response = await self._llmClient.InvokeAsync(
                messages=[
                    ChatMessage.System(_COMPILE_SYSTEM_PROMPT),
                    ChatMessage.User(userMessage),
                ],
                requestParams=LLMRequestParams(temperature=0.3, maxTokens=4096),
                cancellationToken=cancellationToken,
            )
        except Exception as e:
            Logger.Error(f"MemoryCompiler: LLM call failed: {e}")
            return self._CompileFallback(sessions)

        return self._ParseCompileResult(response.content, list(sessions.keys()))

    def _CompileFallback(self, sessions: dict[str, str]) -> list[str]:
        """无 LLM 时的退化编译：将每个会话存为引用记忆。"""
        newPages = []
        for sid, content in sessions.items():
            pageName = f"references-session-{sid[:8]}"
            meta = {
                "category": "reference",
                "page_name": pageName,
                "title": f"Session {sid[:8]}...",
                "confidence": "medium",
                "sources": sid,
                "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            frontmatter = self._store.BuildFrontmatter(meta)
            pageContent = frontmatter + "\n" + content[:2000]
            if self._store.SaveMemoryPage("references", pageName, pageContent):
                self._index.Upsert(
                    pageName, EMemoryCategory.REFERENCE,
                    f"Session {sid[:8]}... summary"
                )
                newPages.append(pageName)

        return newPages

    def _ParseCompileResult(self, llmOutput: str, sourceIds: list[str]) -> list[str]:
        """解析 LLM 输出，写入记忆页面并更新索引。

        LLM 输出格式::

            ---PAGE---
            category: preference
            page_name: coding-style
            title: Python Coding Style
            confidence: high
            sources: session-1, session-2
            ---BODY---
            Use 4-space indentation...
            ---END---
        """
        import re

        newPages = []
        # 按 ---PAGE--- 分割
        pages = re.split(r"\n?---PAGE---\n?", llmOutput)

        for pageBlock in pages:
            pageBlock = pageBlock.strip()
            if not pageBlock or pageBlock == "---NOOP---":
                continue

            # 分离 frontmatter 和 body
            parts = re.split(r"\n?---BODY---\n?", pageBlock, maxsplit=1)
            if len(parts) != 2:
                continue

            metaRaw, bodyRaw = parts
            bodyRaw = re.sub(r"\n?---END---\n?$", "", bodyRaw).strip()
            if not bodyRaw:
                continue

            # 解析 frontmatter
            meta = self._store.ParseFrontmatter("---\n" + metaRaw.strip() + "\n---")[0]

            categoryStr = meta.get("category", "reference")
            pageName = meta.get("page_name", "").strip()
            title = meta.get("title", pageName)
            confidence = meta.get("confidence", "medium")

            if not pageName:
                continue

            # 映射分类（LLM 输出的 category 字符串即目录名，直接构造枚举）
            category = EMemoryCategory.FromDirName(categoryStr.lower()) or EMemoryCategory.REFERENCE

            # 构建最终页面内容
            finalMeta = {
                "title": title,
                "category": categoryStr,
                "confidence": confidence,
                "sources": ", ".join(sourceIds),
                "updated": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            frontmatter = self._store.BuildFrontmatter(finalMeta)
            pageContent = frontmatter + "\n" + bodyRaw

            # 写入
            if self._store.SaveMemoryPage(category.DirName, pageName, pageContent):
                self._index.Upsert(pageName, category, title)
                newPages.append(pageName)
                Logger.Info(f"MemoryCompiler: saved [{category.DirName}] {pageName}")

        return newPages

    def __repr__(self) -> str:
        hasLLM = self._llmClient is not None
        return f"MemoryCompiler(hasLLM={hasLLM}, entries={self._index.EntryCount})"
