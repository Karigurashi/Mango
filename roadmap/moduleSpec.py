"""Roadmap 模块规格 —— 搜索边界与薄结构。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ModuleSpec:
    """单个业务/程序集模块的导航边界。

    roots 是硬事实（目录、asmdef 所在目录、csproj 路径）；
    entrypoints / related / aliases 辅助模糊描述命中与扩搜。
    """

    id: str
    title: str
    aliases: list[str] = field(default_factory=list)
    roots: list[str] = field(default_factory=list)
    entrypoints: list[str] = field(default_factory=list)
    related: list[str] = field(default_factory=list)
    summary: str = ""
    body: str = ""
    sourcePath: str = ""

    def MatchTokens(self) -> list[str]:
        """用于描述匹配的全部文本 token（小写）。"""
        tokens = [self.id, self.title, *self.aliases]
        return [t.strip().lower() for t in tokens if t and t.strip()]
