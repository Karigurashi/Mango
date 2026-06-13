"""RuleComponent —— 将 Rule 管理封装为可挂载的 IComponent。

挂载到 BaseAgent 后，通过 BaseAgent.GetComponent(RuleComponent) 获取
Rule 注册表，支持四种触发模式的规则管理与 Context 注入。
对标 Cursor Rules + Claude Code CLAUDE.md。
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

from agent.core.baseComponent import IComponent
from common.logger import Logger

from .eRuleTriggerMode import ERuleTriggerMode
from .rule import Rule

if TYPE_CHECKING:
    from agent.core.baseAgent import BaseAgent


class RuleComponent(IComponent):
    """Rule 管理组件 —— 持有 Rule 注册表。

    挂载到 BaseAgent 后自动可用，通过 GetComponent(RuleComponent) 获取。
    对标 Cursor Rules 的四种触发模式：
    - ALWAYS_APPLY: 每次注入。
    - GLOB_MATCH: 文件匹配时注入。
    - DESCRIPTION_MATCH: 语义匹配时注入。
    - MANUAL_INVOKE: @rule-name 手动触发。

    用法::

        agent = BaseAgent()
        ruleComp = RuleComponent()
        agent.AddComponent(ruleComp)
        ruleComp.LoadFromDirectory(".cursor/rules")
    """

    def __init__(self) -> None:
        self._rules: dict[str, Rule] = {}

    # ---- 生命周期 ----

    def OnInitialize(self, agent: BaseAgent) -> None:
        """挂载后初始化。"""
        pass

    def OnDestroy(self) -> None:
        """从 BaseAgent 卸载时回调，清空所有已注册 Rule。"""
        self._rules.clear()

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

    # ---- Context 注入 ----

    def GetAlwaysApplyBody(self) -> str:
        """获取所有 AlwaysApply Rule 的合并正文，用于注入 Context。"""
        parts = [r.GetContextInjection() for r in self.GetAlwaysApplyRules()]
        return "\n\n".join(parts)

    def GetMatchedBody(self, filePath: str) -> str:
        """获取所有 glob 匹配当前文件的 Rule 的合并正文。"""
        parts = [r.GetContextInjection() for r in self.MatchGlobs(filePath)]
        return "\n\n".join(parts)

    def MatchManualInvoke(self, userMessage: str) -> list[Rule]:
        """解析 ``@rule-name`` 手动触发语法，返回匹配的 Rule 列表。

        Args:
            userMessage: 用户消息，扫描其中的 ``@name`` 模式。

        Returns:
            匹配的 MANUAL_INVOKE Rule 列表。
        """
        candidates = set(re.findall(r"@(\S+)", userMessage))
        if not candidates:
            return []

        manualRules = self.GetByTriggerMode(ERuleTriggerMode.MANUAL_INVOKE)
        return [r for r in manualRules if r.name in candidates]

    # ---- 批量加载 ----

    def LoadFromDirectory(self, directory: str) -> int:
        """从目录加载所有 .rule.md 文件。

        Returns:
            成功加载的 Rule 数量。
        """
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
                except Exception as exc:
                    Logger.Warning(f"RuleComponent: failed to load rule from {filePath}: {exc}")
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
        return f"RuleComponent(rules={len(self._rules)})"

    def __contains__(self, name: str) -> bool:
        return name in self._rules
