"""ContextAssembler —— 多层 Context 注入管道，连接 extension 与 contex。"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from common.const import ERole

from agent.extension.mcp import McpServerRegistry
from agent.extension.rule import RuleRegistry
from agent.extension.skill import SkillRegistry

from .environmentSnapshot import GetEnvironmentSnapshot

if TYPE_CHECKING:
    from agent.contex.contextEngine import ContextEngine


class ContextAssembler:
    """将 Rule / Skill / MCP / Memory / 环境状态组装为 LOD0 System 块并 Ingest。

    Usage::

        ruleRegistry = RuleRegistry()
        skillRegistry = SkillRegistry()
        mcpServerRegistry = McpServerRegistry()
        ruleRegistry.LoadFromDirectory(".cursor/rules")
        skillRegistry.LoadFromDirectory(".cursor/skills")
        mcpServerRegistry.LoadFromMCPJson(".mcp.json")

        session = Session()
        session.LoadFromMemory(FileMemory())
        engine = ContextEngine(session)
        assembler = ContextAssembler(
            baseSystemPrompt="You are a helpful agent.",
            ruleRegistry=ruleRegistry,
            skillRegistry=skillRegistry,
            mcpServerRegistry=mcpServerRegistry,
        )
        count = await assembler.BuildAsync(engine)
        messages = await engine.AssembleAsync()
    """

    def __init__(
        self,
        baseSystemPrompt: str = "",
        workspaceRoot: str = "",
        activeFilePath: str = "",
        ruleRegistry: RuleRegistry | None = None,
        skillRegistry: SkillRegistry | None = None,
        mcpServerRegistry: McpServerRegistry | None = None,
    ) -> None:
        self._baseSystemPrompt = baseSystemPrompt
        self._workspaceRoot = workspaceRoot or os.getcwd()
        self._activeFilePath = activeFilePath
        self._ruleRegistry = ruleRegistry or RuleRegistry()
        self._skillRegistry = skillRegistry or SkillRegistry()
        self._mcpServerRegistry = mcpServerRegistry or McpServerRegistry()

    @property
    def ruleRegistry(self) -> RuleRegistry:
        return self._ruleRegistry

    @property
    def skillRegistry(self) -> SkillRegistry:
        return self._skillRegistry

    @property
    def mcpServerRegistry(self) -> McpServerRegistry:
        return self._mcpServerRegistry

    async def BuildAsync(
        self,
        engine: "ContextEngine",
        *,
        reloadExtensions: bool = False,
        rulesDir: str | None = None,
        skillsDir: str | None = None,
        mcpJsonPath: str | None = None,
    ) -> int:
        """组装并 Ingest 全部 LOD0 Context 块。

        Args:
            engine: 目标 ContextEngine（消息写入其 Session）。
            reloadExtensions: 是否重新从目录/文件加载 extension 注册表。
            rulesDir: Rule 目录（``*.rule.md``）。
            skillsDir: Skill 目录（``**/SKILL.md``）。
            mcpJsonPath: MCP 配置文件路径（``.mcp.json``）。

        Returns:
            本次 Ingest 的 System 块数量。
        """
        if reloadExtensions:
            self._ReloadExtensions(rulesDir, skillsDir, mcpJsonPath)

        count = 0
        session = engine.Session

        if self._baseSystemPrompt.strip():
            self._IngestSystem(engine, self._baseSystemPrompt, "base")
            count += 1

        if session.memory is not None:
            for block in session.memory.LoadContextBlocks():
                if block.strip():
                    self._IngestSystem(engine, block, "memory")
                    count += 1

        alwaysBody = self._ruleRegistry.GetAlwaysApplyBody()
        if alwaysBody.strip():
            self._IngestSystem(engine, alwaysBody, "rules:always")
            count += 1

        if self._activeFilePath:
            matchedBody = self._ruleRegistry.GetMatchedBody(self._activeFilePath)
            if matchedBody.strip():
                self._IngestSystem(engine, matchedBody, "rules:glob")
                count += 1

        skillPrefixes = self._skillRegistry.GetAllPrefixes()
        if skillPrefixes and skillPrefixes != "No skills available.":
            self._IngestSystem(
                engine,
                f"<available_skills>\n{skillPrefixes}\n</available_skills>",
                "skills",
            )
            count += 1

        mcpDesc = self._mcpServerRegistry.GetToolDescriptions()
        if mcpDesc and mcpDesc != "No MCP servers configured.":
            self._IngestSystem(
                engine,
                f"<mcp_servers>\n{mcpDesc}\n</mcp_servers>",
                "mcp",
            )
            count += 1

        envSnapshot = GetEnvironmentSnapshot(self._workspaceRoot)
        self._IngestSystem(engine, envSnapshot, "environment")
        count += 1

        return count

    @staticmethod
    def _IngestSystem(engine: "ContextEngine", content: str, source: str) -> None:
        """Ingest 一条带来源标记的 System 消息（LOD0）。"""
        engine.Ingest(
            ERole.SYSTEM,
            content,
            metadata={"source": source, "isContextBlock": True},
        )

    def _ReloadExtensions(
        self,
        rulesDir: str | None,
        skillsDir: str | None,
        mcpJsonPath: str | None,
    ) -> None:
        """从文件系统重新加载 extension 注册表。"""
        if rulesDir and os.path.isdir(rulesDir):
            self._ruleRegistry.Clear()
            self._ruleRegistry.LoadFromDirectory(rulesDir)

        if skillsDir and os.path.isdir(skillsDir):
            self._skillRegistry.Clear()
            self._skillRegistry.LoadFromDirectory(skillsDir)

        if mcpJsonPath and os.path.isfile(mcpJsonPath):
            self._mcpServerRegistry.Clear()
            self._mcpServerRegistry.LoadFromMCPJson(mcpJsonPath)

    def __repr__(self) -> str:
        return (
            f"ContextAssembler(workspace={self._workspaceRoot!r}, "
            f"activeFile={self._activeFilePath!r})"
        )
