"""HarnessComponent —— 多层 Context 注入管道，将各组件的 LOD0 块组装后 Ingest 到 ContextComponent。

挂载到 BaseAgent 后自动获取 ContextComponent / RuleComponent / SkillComponent /
McpComponent / ToolComponent / DataComponent，通过 BuildAsync 完成一次性的 LOD0 装填。
"""

from __future__ import annotations

import os
import platform
import sys

from agent.component.contex.contextComponent import ContextComponent
from agent.component.contex.eContextLodLevel import EContextLodLevel
from agent.component.data.dataComponent import DataComponent
from agent.component.mcp.mcpComponent import McpComponent
from agent.component.rule.ruleComponent import RuleComponent
from agent.component.skill.skillComponent import SkillComponent
from agent.component.tool.toolComponent import ToolComponent
from agent.core.baseComponent import IComponent
from common.const import ERole


class HarnessComponent(IComponent):
    """将各 Component 的 LOD0 块组装为 System 消息并 Ingest 到 ContextComponent。

    挂载后通过 BuildAsync 完成一次性装填：
    - skills 前缀 / MCP 工具描述 / Memory 上下文块 / 环境快照

    路径配置（skillsDir / rulesDir / mcpJsonPath / workspaceRoot）统一从
    DataComponent.config（AgentConfig）读取，无需外部传参。

    用法::

        agent = Agent(llm)
        harness = agent.GetComponent(HarnessComponent)
        count = await harness.BuildAsync()
    """

    # ---- IComponent 生命周期 ----

    def OnInitialize(self, agent: BaseAgent) -> None:
        """挂载后初始化，自动注入各依赖 Component。"""
        self._dataComp = agent.GetComponent(DataComponent)
        self._engine = agent.GetComponent(ContextComponent)
        self._ruleComp = agent.GetComponent(RuleComponent)
        self._skillComp = agent.GetComponent(SkillComponent)
        self._mcpComp = agent.GetComponent(McpComponent)
        self._toolComp = agent.GetComponent(ToolComponent)
        self._built = False

    def OnDestroy(self) -> None:
        """从 BaseAgent 卸载时回调，重置构建标记以允许重建。"""
        self._built = False

    # ---- 主入口 ----

    async def BuildAsync(
        self,
        reloadExtensions: bool = True,
    ) -> int:
        """组装并 Ingest 全部 LOD0 Context 块。

        幂等调用：若已成功构建则跳过，避免重复创建 MCP 子进程与重复注册工具。
        可通过 OnDestroy() 重置构建状态后重新调用。

        Args:
            reloadExtensions: 是否从 AgentConfig 指定路径重新加载 extension 注册表。

        Returns:
            本次 Ingest 的 System 块数量。
        """
        if self._built:
            return 0

        if reloadExtensions:
            self._ReloadExtensions()

        count = 0
        session = self._engine.Session

        if session.memory is not None:
            for block in session.memory.LoadContextBlocks():
                if block.strip():
                    self._IngestSystem(block)
                    count += 1

        if self._ruleComp is not None:
            alwaysBody = self._ruleComp.GetAlwaysApplyBody()
            if alwaysBody.strip():
                self._IngestSystem(alwaysBody)
                count += 1

        if self._skillComp is not None:
            skillPrefixes = self._skillComp.GetAllPrefixes()
            if skillPrefixes and skillPrefixes != "No skills available.":
                self._IngestSystem(
                    f"<available_skills>\n{skillPrefixes}\n</available_skills>",
                )
                count += 1

            if self._skillComp.Count() > 0 and self._toolComp is not None:
                from agent.component.skill.loadSkillTool import LoadSkillTool
                loadSkillTool = LoadSkillTool(self._skillComp)
                self._toolComp.RegisterTool(loadSkillTool)

        if self._mcpComp is not None:
            mcpDesc = self._mcpComp.GetToolDescriptions()
            if mcpDesc and mcpDesc != "No MCP servers configured.":
                self._IngestSystem(
                    f"<mcp_servers>\n{mcpDesc}\n</mcp_servers>",
                )
                count += 1

            # 真实连接 MCP Server，发现并注册其工具为可调用工具
            if self._toolComp is not None:
                mcpTools = await self._mcpComp.ConnectAllAsync()
                for mcpTool in mcpTools:
                    self._toolComp.RegisterTool(mcpTool)

        envSnapshot = self._BuildEnvironmentSnapshot()
        self._IngestSystem(envSnapshot)
        count += 1

        self._built = True
        return count

    # ---- 内部 ----

    def _IngestSystem(self, content: str) -> None:
        """Ingest 一条 System 消息（LOD0）。"""
        self._engine.Ingest(
            ERole.SYSTEM,
            content,
            lodLevel=EContextLodLevel.RESIDENT,
        )

    def _BuildEnvironmentSnapshot(self) -> str:
        """生成环境快照文本块。"""
        workspaceRoot = self._dataComp.config.workspaceRoot
        lines = [
            "<environment>",
            f"OS: {platform.system()} {platform.release()}",
            f"Python: {sys.version.split()[0]}",
            f"Workspace: {workspaceRoot}",
            "</environment>",
        ]
        return "\n".join(lines)

    def _ReloadExtensions(self) -> None:
        """从 AgentConfig 指定路径重新加载 extension 注册表。"""
        config = self._dataComp.config

        if config.rulesDir and os.path.isdir(config.rulesDir) and self._ruleComp is not None:
            self._ruleComp.Clear()
            self._ruleComp.LoadFromDirectory(config.rulesDir)

        if config.skillsDir and os.path.isdir(config.skillsDir) and self._skillComp is not None:
            self._skillComp.Clear()
            self._skillComp.LoadFromDirectory(config.skillsDir)

        if config.mcpJsonPath and os.path.isfile(config.mcpJsonPath) and self._mcpComp is not None:
            self._mcpComp.Clear()
            self._mcpComp.LoadFromMCPJson(config.mcpJsonPath)

    def __repr__(self) -> str:
        config = self._dataComp.config if self._dataComp else None
        workspaceRoot = config.workspaceRoot if config else ""
        return f"HarnessComponent(workspace={workspaceRoot!r})"
