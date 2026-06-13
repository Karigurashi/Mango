"""LoadSkill 工具 —— 将 Skill 渐进式披露的 Layer 2 挂载到 ToolComponent。

对标 Claude Code 的 load_skill 工具：
- Layer 1: name + description 已通过 ContextAssembler 注入 system prompt。
- Layer 2: 本工具按名返回 Skill 完整 SOP，结果标记为 LOD1(SUMMARIZABLE)。
- Layer 3: referenceFiles 路径在 SOP 正文中引用，后续按需加载标记为 LOD3(EXTERNAL_ONLY)（当轮注入、次轮丢弃）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent.component.contex.eContextLodLevel import EContextLodLevel
from agent.component.tool.baseTool import BaseTool
from agent.component.tool.eToolCategory import EToolCategory
from agent.component.tool.toolResult import ToolResult

if TYPE_CHECKING:
    from .skillComponent import SkillComponent


class LoadSkillTool(BaseTool):
    """按名称加载 Skill 完整 SOP 正文的工具。

    结果 LOD 等级 = SUMMARIZABLE（LOD1）：可压缩但不可丢弃，
    确保 LLM 在执行过程中始终保留 Skill 的核心工作流指令。
    """

    name = "load_skill"
    description = (
        "Load a skill's full instructions by name. "
        "Call this when a skill's description suggests it is relevant "
        "to the current task. Returns the skill's complete SOP."
    )
    category = EToolCategory.KNOWLEDGE
    parameters = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "The name of the skill to load.",
            },
        },
        "required": ["name"],
    }
    resultLodLevel = EContextLodLevel.SUMMARIZABLE

    def __init__(self, skillComponent: "SkillComponent") -> None:
        super().__init__()
        self._skillComponent = skillComponent

    def _Invoke(self, name: str) -> ToolResult:
        """加载指定 Skill 的完整 SOP。

        Args:
            name: Skill 名称（对应 SKILL.md frontmatter 中的 name 字段）。

        Returns:
            ToolResult: 成功时 content 为带 <skill> 标签包裹的 SOP 正文。
        """
        content = self._skillComponent.LoadSkill(name)
        if content.startswith("Error:"):
            return ToolResult.Fail(content, toolName=self.name)
        return ToolResult.Ok(content, toolName=self.name)
