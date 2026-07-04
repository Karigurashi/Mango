"""agent/contex —— 上下文管理模块。

基于 LOD 四级分级系统的上下文管理：
- ContextComponent: 四阶段编排（Ingest/Assemble/Compact/AfterTurn）
- ContextCompactor: LLM 驱动的批量上下文摘要压缩
"""

from .contextComponent import ContextComponent
from .contextMessage import ContextMessage
from .contextCompactor import CompactionResult, ContextCompactor
from .eContextLodLevel import EContextLodLevel

__all__ = [
    "CompactionResult",
    "ContextComponent",
    "ContextMessage",
    "ContextCompactor",
    "EContextLodLevel",
]
