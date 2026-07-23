"""Code Roadmap —— 模块边界导航 + 范围内 grep（独立于 Agent）。

面向外部 Unity/C# 大仓：用业务模块锁定 roots，再 rg，避免全仓搜索跑偏。
"""

from .moduleSpec import ModuleSpec
from .roadmapStore import RoadmapStore
from .resolver import ModuleResolver, ResolveHit

__all__ = [
    "ModuleSpec",
    "RoadmapStore",
    "ModuleResolver",
    "ResolveHit",
]
