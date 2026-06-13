"""MemoryComponent —— Karpathy LLM Wiki 风格的跨会话持久化记忆组件。

作为 IComponent 可挂载到 BaseAgent，通过 OnInitialize/OnDestroy 感知生命周期。
挂载后自动从 Agent 获取 LLMComponent 注入 LLM 能力，启用 CompileAsync / LintAsync。

目录结构（位于 workspace/memory/）::

    {workspace/memory/}/
        sessions/               # 不可变会话摘要
            {sessionId}.md
        memory/                 # LLM 编译的持久记忆
            INDEX.md            # 导航索引（LOD0 注入入口）
            LOG.md              # 追加式操作日志
            preferences/        # 用户偏好
            decisions/          # 架构决策
            patterns/           # 反馈模式
            references/         # 外部引用
        checkpoints/            # 工作流断点存档

使用方式::

    # Component 模式
    agent.AddComponent(MemoryComponent)

    # 纯文件 I/O
    memComp.SaveSessionSummary("abc123", "用户偏好 4 空格缩进")
    blocks = memComp.LoadContextBlocks()

    # LLM 增强模式（挂载到 Agent 后自动可用）
    await memComp.CompileAsync()
    report = await memComp.LintAsync()
"""

from __future__ import annotations

import time
from typing import Optional, TYPE_CHECKING

from agent.core.baseComponent import IComponent
from common.cancellationToken import CancellationToken
from common.const import ERoad
from common.logger import Logger

if TYPE_CHECKING:
    from agent.core.baseAgent import BaseAgent


class MemoryComponent(IComponent):
    """Karpathy LLM Wiki 风格的文件后端记忆组件。

    挂载到 BaseAgent 后自动可用，卸载时清理内部引用。

    Attributes:
        Store: 底层 MemoryStore（供 CheckpointManager 等使用）。
        Index: 底层 MemoryIndex。
        StorageDir: 记忆根目录路径。
        HasLLM: 是否已注入 LLM 能力。
    """

    def __init__(self) -> None:
        self._store = None
        self._index = None
        self._compiler = None
        self._lint = None

    # ---- IComponent 生命周期 ----

    def OnInitialize(self, agent: BaseAgent) -> None:
        """挂载后初始化，创建存储和索引并自动注入 LLM 能力。

        从 DataComponent.config 获取配置，若 Agent 已挂载 LLMComponent 则自动启用 CompileAsync / LintAsync。
        """
        from agent.component.data.dataComponent import DataComponent
        from .memoryStore import MemoryStore
        from .memoryIndex import MemoryIndex

        dataComp = agent.GetComponent(DataComponent)
        configuredDir = dataComp.config.memoryDir if dataComp is not None else ""
        memoryDir = configuredDir or str(ERoad.MEMORY_DIR)

        self._store = MemoryStore(memoryDir)
        self._index = MemoryIndex(self._store)
        self._TryInjectLLM(agent)

    def OnDestroy(self) -> None:
        """从 BaseAgent 卸载时回调，清理 LLM 引用。"""
        self._compiler = None
        self._lint = None

    # ---- LLM 能力注入 ----

    def _TryInjectLLM(self, agent: BaseAgent) -> None:
        """尝试从 Agent 获取 LLMComponent 并注入 LLM 能力。"""
        try:
            from agent.component.llm.llmComponent import LLMComponent
            llmComp = agent.GetComponent(LLMComponent)
            if llmComp is not None:
                from .memoryCompiler import MemoryCompiler
                from .memoryLint import MemoryLint
                self._compiler = MemoryCompiler(self._store, self._index, llmComp)
                self._lint = MemoryLint(self._store, self._index, llmComp)
        except Exception as exc:
            Logger.Warning(
                f"MemoryComponent: LLM injection failed, "
                f"CompileAsync/LintAsync will run in degraded mode: {exc}"
            )

    # ---- Context 注入 ----

    def LoadContextBlocks(self) -> list[str]:
        """从 INDEX.md 加载 LOD0 上下文块。

        只加载 INDEX.md（< 500 tokens），不含具体页面内容。
        ContextAssembler 按需读取具体的 memory/*.md。
        """
        return self._index.ToContextBlocks()

    # ---- Session 持久化 ----

    def SaveSessionSummary(
        self,
        sessionId: str,
        summary: str,
        messageCount: int = 0,
        compactedCount: int = 0,
        compressedUpToTurnIndex: int = -1,
    ) -> None:
        """保存会话摘要到 sessions/{sessionId}.md，含完整压缩元数据。

        纯文件 I/O，不调 LLM。同时写入 LOG.md 记录操作。
        保存后自动触发会话裁剪（超出 MAX_SESSIONS 时删除最旧 PRUNE_COUNT 条）。
        """
        if not summary.strip():
            return

        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        hasCompression = compressedUpToTurnIndex >= 0

        meta = {
            "session_id": sessionId,
            "created": now,
            "message_count": str(messageCount),
            "compacted_count": str(compactedCount),
            "has_compression": str(hasCompression).lower(),
            "compressed_up_to_turn": str(compressedUpToTurnIndex),
        }
        frontmatter = self._store.BuildFrontmatter(meta)

        bodyLines = [
            f"# Session {sessionId[:8]}...",
            "",
            f"**Messages**: {messageCount} | **Compacted**: {compactedCount}",
        ]
        if hasCompression:
            bodyLines.append(f"**Compressed up to turn**: {compressedUpToTurnIndex}")
        else:
            bodyLines.append("**Compression**: none")
        bodyLines.append("")
        bodyLines.append("## Summary")
        bodyLines.append(summary)

        content = frontmatter + "\n".join(bodyLines)

        if self._store.SaveSession(sessionId, content):
            compressedStr = f"turn{compressedUpToTurnIndex}" if hasCompression else "none"
            self._store.AppendLog(
                f"Saved session: {sessionId[:8]}... "
                f"(msgs={messageCount}, compacted={compactedCount}, "
                f"compressed={compressedStr})"
            )
            Logger.Info(f"MemoryComponent: saved session {sessionId[:8]}...")

    def SaveContextBlocks(self, blocks: list[str]) -> None:
        """持久化用户自定义 Context 块 — 写入 references/user-blocks.md。"""
        if not blocks:
            return

        from .eMemoryCategory import EMemoryCategory

        meta = {
            "title": "User-defined Context Blocks",
            "category": "reference",
            "confidence": "high",
            "updated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        frontmatter = self._store.BuildFrontmatter(meta)
        body = "\n\n".join(f"## Block {i+1}\n{b}" for i, b in enumerate(blocks))
        content = frontmatter + "\n# User Context Blocks\n\n" + body

        self._store.SaveMemoryPage("references", "user-blocks", content)
        self._index.Upsert(
            "references-user-blocks",
            EMemoryCategory.REFERENCE,
            "User-defined context blocks"
        )

    # ---- 记忆编译 ----

    async def CompileAsync(
        self,
        sessionIds: list[str] | None = None,
        cancellationToken: Optional[CancellationToken] = None,
    ) -> list[str]:
        """LLM 驱动的记忆编译。

        若未注入 LLMClient，退化为简单摘要追加。
        """
        if self._compiler is None:
            from .memoryCompiler import MemoryCompiler
            self._compiler = MemoryCompiler(self._store, self._index, llmClient=None)

        return await self._compiler.CompileAsync(sessionIds, cancellationToken)

    # ---- 健康检查 ----

    async def LintAsync(self) -> dict:
        """记忆健康检查。

        若未注入 LLMClient，仅执行规则检查（孤页、死链、过期）。
        """
        if self._lint is None:
            from .memoryLint import MemoryLint
            self._lint = MemoryLint(self._store, self._index, llmClient=None)

        return await self._lint.RunAsync()

    # ---- 辅助查询 ----

    def LoadSession(self, sessionId: str) -> str | None:
        """读取指定会话摘要。"""
        return self._store.LoadSession(sessionId)

    def LoadMemoryPage(self, categoryDir: str, pageName: str) -> str | None:
        """读取指定记忆页面内容。"""
        return self._store.LoadMemoryPage(categoryDir, pageName)

    def FindMemoryPages(self, keyword: str) -> list[str]:
        """按关键词搜索记忆页面名（简单子串匹配，不调 LLM）。"""
        results = []
        for pageName, (_cat, desc) in self._index.GetAll().items():
            if keyword.lower() in pageName.lower() or keyword.lower() in desc.lower():
                results.append(pageName)
        return results

    # ---- 属性 ----

    @property
    def Store(self):
        """获取底层 MemoryStore（供 CheckpointManager 等使用）。"""
        return self._store

    @property
    def Index(self):
        """获取底层 MemoryIndex。"""
        return self._index

    @property
    def StorageDir(self) -> str:
        return self._store.BaseDir

    @property
    def HasLLM(self) -> bool:
        return self._compiler is not None and self._compiler.HasLLM

    # ---- 表示 ----

    def __repr__(self) -> str:
        return (
            f"MemoryComponent(dir={self._store.BaseDir!r}, "
            f"entries={self._index.EntryCount}, "
            f"hasLLM={self.HasLLM})"
        )
