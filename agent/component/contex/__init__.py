"""agent/contex —— 上下文管理模块。

基于 LOD 四级分级系统的上下文管理：
- ContextComponent: 四阶段编排（Ingest/Assemble/Compact/AfterTurn）
- ContextLodManager: LOD 分级核心（分类/过滤/压缩）
"""

from .contextComponent import ContextComponent
from .contextLodManager import ContextLodManager
from .contextMessage import ContextMessage
from .contentStore import ContentStore
from .contextCompactor import CompactionResult, ContextCompactor, ECompactionUrgency
from .eContextLodLevel import EContextLodLevel

__all__ = [
    "CompactionResult",
    "ContextComponent",
    "ContextLodManager",
    "ContextMessage",
    "ContentStore",
    "ContextCompactor",
    "ECompactionUrgency",
    "EContextLodLevel",
]
