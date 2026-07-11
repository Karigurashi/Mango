"""内部共享任务调度器。"""

from __future__ import annotations

import asyncio
from typing import Optional, TypeVar

from .baseScheduler import BaseScheduler
from .task import ETaskStatus, Task
from .taskHandle import TaskDoneCallback, TaskHandle

DEFAULT_MAX_TASKS = 500

TTask = TypeVar("TTask", bound=Task)


class _TaskScheduler(BaseScheduler):
    """共享底层调度器，只负责把 Task 跑起来。"""

    def __init__(self, maxTasks: int = DEFAULT_MAX_TASKS) -> None:
        self._handles: dict[int, TaskHandle] = {}
        self._maxTasks: int = maxTasks

    def Schedule(
        self,
        task: TTask,
        onFinished: TaskDoneCallback | None = None,
    ) -> TaskHandle[TTask]:
        """调度一个任务，返回可等待/可取消的执行句柄。"""
        self._EnsureEventLoop()
        while len(self._handles) >= self._maxTasks:
            self._EvictLRU()

        handle = self._CreateHandle(task, onFinished)
        self._handles[task.info.taskId] = handle
        handle.asyncioTask = asyncio.create_task(self._ExecuteAsync(handle))
        return handle

    def GetHandle(self, taskId: int) -> Optional[TaskHandle]:
        """按 taskId 获取执行句柄。"""
        handle = self._handles.get(taskId)
        if handle is not None:
            self._BumpAccess(handle)
        return handle

    def Cancel(self, taskId: int) -> bool:
        """取消指定运行中任务。"""
        handle = self._handles.get(taskId)
        if handle is None:
            return False
        return handle.Cancel()

    def _EvictLRU(self) -> None:
        if not self._handles:
            return
        doneHandles = {
            tid: h
            for tid, h in self._handles.items()
            if h.task.info.status != ETaskStatus.RUNNING
        }
        source = doneHandles if doneHandles else dict(self._handles)
        lruId = min(source, key=lambda tid: source[tid].lastAccessedAt)
        handle = self._handles.pop(lruId)
        if handle.asyncioTask is not None and not handle.asyncioTask.done():
            handle.asyncioTask.cancel()
        if handle.cancellationToken is not None:
            handle.cancellationToken.Cancel()


_DEFAULT_TASK_SCHEDULER = _TaskScheduler()

