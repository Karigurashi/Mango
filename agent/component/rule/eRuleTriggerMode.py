"""Rule 触发模式枚举 —— 控制 Rule 在何种条件下被注入 Context。"""

from enum import Enum


class ERuleTriggerMode(Enum):
    """Rule 的四种触发策略，对标 Cursor Rules 的 frontmatter 驱动模式。

    Attributes:
        ALWAYS_APPLY: 每次 Session 必定注入，忽略 globs 和 description。
        GLOB_MATCH: 当前上下文中文件匹配 globs 模式时自动注入。
        DESCRIPTION_MATCH: Agent 根据 description 语义判断相关性后注入。
        MANUAL_INVOKE: 仅通过 @rule-name 手动触发时注入。
    """

    ALWAYS_APPLY = "alwaysApply"
    GLOB_MATCH = "globMatch"
    DESCRIPTION_MATCH = "descriptionMatch"
    MANUAL_INVOKE = "manualInvoke"
