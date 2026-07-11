"""TaskProgressData —— Workflow PROGRESS 事件载荷。"""

from __future__ import annotations

from dataclasses import dataclass

from .eTaskProgressKind import ETaskProgressKind


@dataclass(slots=True)
class TaskProgressData:
    """Workflow 进度/流式数据。"""

    kind: ETaskProgressKind
    nodeId: int = 0
    agentId: int = 0
    message: str = ""
    status: str = ""

