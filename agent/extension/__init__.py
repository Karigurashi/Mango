"""Agent Extension —— Agent 扩展能力层。

提供 Rule、MCP、Skill 三大扩展机制的统一入口，由外部 Harness 层决定加载和注入策略。

子模块:
    - rule:  Agent 行为规则（对标 Cursor Rules + Claude Code CLAUDE.md）。
    - mcp:   MCP Server 配置管理（对标 Claude Code MCP 命令体系）。
    - skill: Agent 技能管理（对标 Claude Code SKILL.md 渐进式披露）。
"""

from .rule import ERuleTriggerMode, Rule, RuleRegistry
from .mcp import EMcpTransport, McpServerConfig, McpServerRegistry
from .skill import Skill, SkillLoader, SkillRegistry

__all__ = [
    # Rule
    "ERuleTriggerMode",
    "Rule",
    "RuleRegistry",
    # MCP
    "EMcpTransport",
    "McpServerConfig",
    "McpServerRegistry",
    # Skill
    "Skill",
    "SkillLoader",
    "SkillRegistry",
]
