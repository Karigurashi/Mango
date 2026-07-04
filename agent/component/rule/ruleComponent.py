"""RuleComponent —— 将所有规则文件直接注入 Context。

挂载到 BaseAgent 后，通过 BaseAgent.GetComponent(RuleComponent) 获取。
直接加载 rulesDir 目录下的 .md / .mdc 文件，全部注入为常驻 System Prompt。
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from agent.core.baseComponent import IComponent
from common.logger import Logger

if TYPE_CHECKING:
    from agent.core.baseAgent import BaseAgent


class RuleComponent(IComponent):
    """Rule 管理组件 —— 直接加载文件夹下的 .md/.mdc 文件全部注入。

    用法::

        agent = BaseAgent()
        ruleComp = RuleComponent()
        agent.AddComponent(ruleComp)
        ruleComp.LoadFromDirectory("workspace/rules")
    """

    def __init__(self) -> None:
        self._bodies: list[str] = []

    # ---- 生命周期 ----

    def OnInitialize(self, agent: BaseAgent) -> None:
        """挂载后初始化。"""
        pass

    def OnDestroy(self) -> None:
        """从 BaseAgent 卸载时回调，清空所有已加载规则。"""
        self._bodies.clear()

    # ---- Context 注入 ----

    def GetAlwaysApplyBody(self) -> str:
        """获取所有已加载规则的合并正文，用于注入 Context。"""
        return "\n\n".join(self._bodies)

    # ---- 批量加载 ----

    def LoadFromDirectory(self, directory: str) -> int:
        """从目录加载所有 .md / .mdc 文件。

        Returns:
            成功加载的文件数量。
        """
        count = 0
        if not os.path.isdir(directory):
            return count

        for root, _dirs, files in os.walk(directory):
            for filename in files:
                if not (filename.endswith(".md") or filename.endswith(".mdc")):
                    continue
                filePath = os.path.join(root, filename)
                try:
                    with open(filePath, "r", encoding="utf-8") as f:
                        body = f.read()
                    if body.strip():
                        self._bodies.append(body.strip())
                        count += 1
                except Exception as exc:
                    Logger.Warning(f"RuleComponent: failed to load rule from {filePath}: {exc}")
                    continue

        return count

    # ---- 查询 ----

    def GetAll(self) -> list[dict]:
        """获取所有已加载规则的简略信息列表。"""
        return [{"body": body} for body in self._bodies]

    # ---- 管理 ----

    def Count(self) -> int:
        """已加载规则总数。"""
        return len(self._bodies)

    def Clear(self) -> None:
        """清空所有已加载规则。"""
        self._bodies.clear()

    # ---- 魔法方法 ----

    def __repr__(self) -> str:
        return f"RuleComponent(rules={len(self._bodies)})"
