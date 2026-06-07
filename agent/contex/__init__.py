"""agent/contex —— 上下文管理模块。

基于 LOD 四级分级系统的上下文管理：
- Session: Memory 与 AI 对话之间的内存缓冲区
- ContextEngine: 四阶段编排（Ingest/Assemble/Compact/AfterTurn）
- ContextLodManager: LOD 分级核心（分类/过滤/压缩）
"""

from .contextConfig import ContextConfig
from .contextEngine import ContextEngine
from .contextLodManager import ContextLodManager
from .contextMessage import ContextMessage
from .contentStore import ContentStore
from .contextCompactor import CompactionResult, ContextCompactor
from .eCompactionUrgency import ECompactionUrgency
from .eContextLodLevel import EContextLodLevel
from .eSubagentContextMode import ESubagentContextMode
from .session import Session
from .subagentContext import SubagentContext
from .tokenEstimator import TokenEstimator

__all__ = [
    "CompactionResult",
    "ContextConfig",
    "ContextEngine",
    "ContextLodManager",
    "ContextMessage",
    "ContentStore",
    "ContextCompactor",
    "ECompactionUrgency",
    "EContextLodLevel",
    "ESubagentContextMode",
    "Session",
    "SubagentContext",
    "TokenEstimator",
]
