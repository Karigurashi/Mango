"""Agent Extension Rule —— Agent 规则管理模块。

对标 Cursor Rules + Claude Code CLAUDE.md，提供：
    - Rule: 单条规则的元数据 + 正文封装。
    - ERuleTriggerMode: 四种触发模式（AlwaysApply / GlobMatch / DescriptionMatch / ManualInvoke）。
    - RuleRegistry: 注册表，支持注册、查询、glob 匹配、目录批量加载。
"""

from .eRuleTriggerMode import ERuleTriggerMode
from .rule import Rule
from .ruleRegistry import RuleRegistry

__all__ = [
    "ERuleTriggerMode",
    "Rule",
    "RuleRegistry",
]
