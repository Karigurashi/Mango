"""Rule 注册表 —— 管理 Agent 规则，支持注册、查询、条件匹配。"""

from __future__ import annotations

from .eRuleTriggerMode import ERuleTriggerMode
from .rule import Rule


class RuleRegistry:
    """按名称索引 Rule 的注册表，每个 Agent 持有一份独立实例。

    用法::

        registry = RuleRegistry()

        rule = Rule.FromMarkdown(source, "projectRule.md")
        registry.Register(rule)

        # 查询
        alwaysRules = registry.GetByTriggerMode(ERuleTriggerMode.ALWAYS_APPLY)
        matched = registry.MatchGlobs("src/components/Button.tsx")
        allPrefixes = registry.GetAllPrefixes()
    """

    def __init__(self) -> None:
        self._rules: dict[str, Rule] = {}

    # ---- 注册 ----

    def Register(self, rule: Rule) -> None:
        """注册一条 Rule（同名覆盖）。"""
        if not rule.name:
            raise ValueError("Rule must have a non-empty name")
        self._rules[rule.name] = rule

    def Unregister(self, name: str) -> None:
        """移除指定 Rule。"""
        self._rules.pop(name, None)

    # ---- 查询 ----

    def Get(self, name: str) -> Rule | None:
        """按名称获取 Rule。"""
        return self._rules.get(name)

    def GetAll(self) -> dict[str, Rule]:
        """获取所有已注册 Rule 的副本。"""
        return dict(self._rules)

    def GetByTriggerMode(self, triggerMode: ERuleTriggerMode) -> list[Rule]:
        """按触发模式筛选 Rule。"""
        return [r for r in self._rules.values() if r.triggerMode == triggerMode]

    # ---- 条件匹配 ----

    def MatchGlobs(self, filePath: str) -> list[Rule]:
        """返回所有 glob 匹配当前文件路径的 Rule。"""
        return [r for r in self._rules.values() if r.MatchesGlob(filePath)]

    def GetAlwaysApplyRules(self) -> list[Rule]:
        """获取所有始终应用的 Rule。"""
        return self.GetByTriggerMode(ERuleTriggerMode.ALWAYS_APPLY)

    def GetDescriptionMatchRules(self) -> list[Rule]:
        """获取所有按语义匹配的 Rule。"""
        return self.GetByTriggerMode(ERuleTriggerMode.DESCRIPTION_MATCH)

    # ---- Context 注入辅助 ----

    def GetAllPrefixes(self) -> str:
        """获取所有 Rule 的轻量前缀（~100 tokens/rule），用于注入 system prompt。"""
        if not self._rules:
            return "No rules configured."
        lines = [r.GetContextPrefix() for r in self._rules.values()]
        return "\n".join(lines)

    def GetAlwaysApplyBody(self) -> str:
        """获取所有 AlwaysApply Rule 的合并正文，用于注入 Context。"""
        parts = [r.GetContextInjection() for r in self.GetAlwaysApplyRules()]
        return "\n\n".join(parts)

    def GetMatchedBody(self, filePath: str) -> str:
        """获取所有 glob 匹配当前文件的 Rule 的合并正文。"""
        parts = [r.GetContextInjection() for r in self.MatchGlobs(filePath)]
        return "\n\n".join(parts)

    # ---- 批量加载 ----

    def LoadFromDirectory(self, directory: str) -> int:
        """从目录加载所有 .rule.md 文件。

        Returns:
            成功加载的 Rule 数量。
        """
        import os

        count = 0
        if not os.path.isdir(directory):
            return count

        for root, _dirs, files in os.walk(directory):
            for filename in files:
                if not filename.endswith(".rule.md"):
                    continue
                filePath = os.path.join(root, filename)
                try:
                    with open(filePath, "r", encoding="utf-8") as f:
                        source = f.read()
                    rule = Rule.FromMarkdown(source, sourcePath=filePath)
                    if not rule.name:
                        rule.name = os.path.splitext(os.path.basename(filePath))[0]
                    self.Register(rule)
                    count += 1
                except Exception:
                    continue

        return count

    # ---- 管理 ----

    def Count(self) -> int:
        """已注册 Rule 总数。"""
        return len(self._rules)

    def Clear(self) -> None:
        """清空所有注册（谨慎使用）。"""
        self._rules.clear()

    # ---- 魔法方法 ----

    def __repr__(self) -> str:
        return f"RuleRegistry(rules={len(self._rules)})"

    def __contains__(self, name: str) -> bool:
        return name in self._rules
