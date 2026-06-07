"""Rule 数据对象 —— 封装一条 Agent 规则的元数据与正文。

对标 Cursor 的 .mdc 文件和 Claude Code 的 CLAUDE.md 指令：
每条 Rule 由 YAML frontmatter 元数据 + Markdown 正文组成，
元数据决定触发策略，正文在注入 Context 时展开。
"""

from __future__ import annotations

from typing import Any

from .eRuleTriggerMode import ERuleTriggerMode


class Rule:
    """单条 Agent 规则，包含元数据与正文。

    Attributes:
        name: 规则名称（唯一标识）。
        description: 规则描述，用于 Agent 语义匹配。
        triggerMode: 触发模式枚举。
        globs: glob 模式列表（GLOB_MATCH 模式时生效）。
        alwaysApply: 是否始终应用（兼容 Cursor 格式的冗余字段）。
        body: 规则正文（Markdown）。
        sourcePath: 规则文件的来源路径（可选）。
    """

    def __init__(
        self,
        name: str,
        description: str = "",
        triggerMode: ERuleTriggerMode = ERuleTriggerMode.MANUAL_INVOKE,
        globs: list[str] | None = None,
        alwaysApply: bool = False,
        body: str = "",
        sourcePath: str = "",
    ) -> None:
        self.name = name
        self.description = description
        self.triggerMode = triggerMode
        self.globs = globs or []
        self.alwaysApply = alwaysApply
        self.body = body
        self.sourcePath = sourcePath

    # ---- 序列化 ----

    def ToDict(self) -> dict[str, Any]:
        """导出为可序列化的字典。"""
        return {
            "name": self.name,
            "description": self.description,
            "triggerMode": self.triggerMode.value,
            "globs": self.globs,
            "alwaysApply": self.alwaysApply,
            "body": self.body,
            "sourcePath": self.sourcePath,
        }

    @staticmethod
    def FromDict(data: dict[str, Any]) -> "Rule":
        """从字典反序列化。"""
        return Rule(
            name=data.get("name", ""),
            description=data.get("description", ""),
            triggerMode=ERuleTriggerMode(data.get("triggerMode", "manualInvoke")),
            globs=data.get("globs", []),
            alwaysApply=data.get("alwaysApply", False),
            body=data.get("body", ""),
            sourcePath=data.get("sourcePath", ""),
        )

    # ---- Frontmatter 解析 ----

    @staticmethod
    def FromMarkdown(source: str, sourcePath: str = "") -> "Rule":
        """从带 YAML frontmatter 的 Markdown 字符串解析 Rule。

        兼容 Claude Code SKILL.md 和 Cursor .mdc 两种格式的 frontmatter。
        格式示例::

            ---
            name: my-rule
            description: 前端组件规范
            alwaysApply: false
            globs:
              - src/components/**/*.tsx
            ---

            # 规则正文 ...

        Args:
            source: 带 frontmatter 的 Markdown 全文。
            sourcePath: 文件来源路径（可选）。
        """
        meta, body = Rule._ParseFrontmatter(source)

        name = meta.get("name", "")
        description = meta.get("description", "")
        alwaysApply = meta.get("alwaysApply", False)
        globsRaw = meta.get("globs", [])

        # 标准化 globs
        if isinstance(globsRaw, str):
            globs = [g.strip() for g in globsRaw.split(",") if g.strip()]
        elif isinstance(globsRaw, list):
            globs = globsRaw
        else:
            globs = []

        # 推断触发模式
        triggerMode = Rule._InferTriggerMode(alwaysApply, description, globs)

        return Rule(
            name=name,
            description=description,
            triggerMode=triggerMode,
            globs=globs,
            alwaysApply=alwaysApply,
            body=body.strip(),
            sourcePath=sourcePath,
        )

    # ---- 工具方法 ----

    def GetContextInjection(self) -> str:
        """获取注入 Context 的完整文本。"""
        return self.body

    def GetContextPrefix(self) -> str:
        """获取注入 Context 的轻量前缀（~100 tokens）。"""
        return f"- {self.name}: {self.description}"

    def MatchesGlob(self, filePath: str) -> bool:
        """检查给定文件路径是否匹配任一 glob 模式。

        支持 ``*`` 和 ``**`` 通配符，将 glob 模式转为正则匹配。
        """
        if not self.globs:
            return False
        import re
        for pat in self.globs:
            regex = self._GlobToRegex(pat)
            if re.match(regex, filePath):
                return True
        return False

    @staticmethod
    def _GlobToRegex(pattern: str) -> str:
        """将 glob 模式转换为正则表达式。

        - ``*`` 匹配单层路径段（不含 ``/``）。
        - ``**`` 匹配任意层级路径。
        - ``**/`` 匹配零或多个目录层级。
        """
        import re

        result = "^"
        i = 0
        n = len(pattern)
        while i < n:
            c = pattern[i]
            if c == "*":
                # 检查是否为 **
                if i + 1 < n and pattern[i + 1] == "*":
                    if i + 2 < n and pattern[i + 2] == "/":
                        # **/ : 零或多个目录层级
                        result += "(?:.*?/)*"
                        i += 3
                        continue
                    else:
                        # 独立的 ** : 匹配任意内容
                        result += ".*"
                        i += 2
                        continue
                else:
                    # 单个 * : 匹配不含 / 的文件名段
                    result += "[^/]*"
                    i += 1
                    continue
            elif c in ".^${}()|+\\[]":
                result += "\\" + c
                i += 1
            else:
                result += c
                i += 1
        result += "$"
        return result

    # ---- 内部方法 ----

    @staticmethod
    def _ParseFrontmatter(source: str) -> tuple[dict[str, Any], str]:
        """解析 YAML frontmatter。

        Returns:
            (meta字典, body字符串)
        """
        import yaml

        source = source.strip()
        if not source.startswith("---"):
            return {}, source

        parts = source.split("---", 2)
        if len(parts) < 3:
            return {}, source

        try:
            meta = yaml.safe_load(parts[1]) or {}
        except Exception:
            meta = {}

        body = parts[2].strip()
        return meta, body

    @staticmethod
    def _InferTriggerMode(
        alwaysApply: bool,
        description: str,
        globs: list[str],
    ) -> ERuleTriggerMode:
        """根据 frontmatter 字段推断触发模式。"""
        if alwaysApply:
            return ERuleTriggerMode.ALWAYS_APPLY
        if globs:
            return ERuleTriggerMode.GLOB_MATCH
        if description:
            return ERuleTriggerMode.DESCRIPTION_MATCH
        return ERuleTriggerMode.MANUAL_INVOKE

    # ---- 魔法方法 ----

    def __repr__(self) -> str:
        return (
            f"Rule(name={self.name!r}, triggerMode={self.triggerMode.value}, "
            f"globs={len(self.globs)}, bodyLen={len(self.body)})"
        )
