"""Agent Extension Skill —— Agent 技能管理模块。

对标 Claude Code SKILL.md 的渐进式披露架构，提供：
    - Skill: 单条技能的元数据 + SOP 正文封装。
    - SkillLoader: 文件系统扫描器，递归加载 SKILL.md。
    - SkillRegistry: 注册表，内置 load_skill 工具定义。
"""

from .skill import Skill
from .skillLoader import SkillLoader
from .skillRegistry import SkillRegistry

__all__ = [
    "Skill",
    "SkillLoader",
    "SkillRegistry",
]
