"""Task —— 可执行任务本体。"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import IntEnum
from typing import TYPE_CHECKING, ClassVar, Generic, Optional, TypeVar, cast

if TYPE_CHECKING:
    from common.cancellationToken import CancellationToken
    from .taskHandle import TaskDoneCallback
    from .taskHandle import TaskHandle

TResult = TypeVar("TResult")
TTask = TypeVar("TTask", bound="Task")


class ETaskStatus(IntEnum):
    """任务运行时状态。"""

    RUNNING = 0
    COMPLETED = 1
    FAILED = 2
    CANCELLED = 3


@dataclass(slots=True)
class TaskInfo:
    """任务的通用身份与一次执行状态。"""

    taskId: int
    createdAt: float
    name: str = "Unnamed"
    status: ETaskStatus = ETaskStatus.RUNNING
    error: str = ""


class Task:
    """可执行任务基类。

    运行态由 TaskHandle 持有，Task 本身不承载调度器私有字段。
    """

    _nextId: ClassVar[int] = 0

    def __init__(self, name: str = "") -> None:
        Task._nextId += 1
        self._info: TaskInfo = TaskInfo(
            taskId=Task._nextId,
            createdAt=time.time(),
            name=name or "Unnamed",
        )

    @property
    def info(self) -> TaskInfo:
        """只读 TaskInfo 引用，供序列化 / 日志等场景。"""
        return self._info

    async def ExecuteAsync(self, cancellationToken: Optional["CancellationToken"] = None) -> None:
        """执行任务核心逻辑，子类 override。"""
        raise NotImplementedError

    def RunAsync(self: TTask, onFinished: Optional["TaskDoneCallback"] = None) -> "TaskHandle[TTask]":
        """使用内部共享调度器调度当前任务。"""
        from .taskScheduler import _DEFAULT_TASK_SCHEDULER
        return _DEFAULT_TASK_SCHEDULER.Schedule(self, onFinished=onFinished)

    def __await__(self):
        return self.RunAsync().WaitAsync().__await__()


class TaskT(Task, Generic[TResult]):
    """类似 C# Task<T> 的带结果任务基类。"""

    def __init__(self, name: str = "") -> None:
        super().__init__(name=name)
        self._hasResult: bool = False
        self._result: TResult | None = None

    @property
    def result(self) -> TResult:
        if not self._hasResult:
            raise RuntimeError(f"Task {self.info.taskId} has not produced a result")
        return cast(TResult, self._result)

    async def ExecuteAsync(self, cancellationToken: Optional["CancellationToken"] = None) -> TResult:
        """执行任务核心逻辑，子类 override 并返回结果。"""
        raise NotImplementedError
