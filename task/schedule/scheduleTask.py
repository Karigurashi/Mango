"""ScheduleTask —— 由全局 CronScheduler 驱动的定时 Task。"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Optional

from common.cancellationToken import CancellationToken
from task.core.task import TaskT
from .taskSpec import TaskSpec

if TYPE_CHECKING:
    from task.core.taskHandle import TaskDoneCallback, TaskHandle


class ScheduleTask(TaskT[TaskSpec]):
    """定时任务：RunAsync 注册到全局 CronScheduler，到期后执行。"""

    def __init__(self, taskSpec: TaskSpec) -> None:
        super().__init__(name=taskSpec.name or "ScheduleTask")
        self.taskSpec: TaskSpec = taskSpec

    async def ExecuteAsync(
        self,
        cancellationToken: Optional[CancellationToken] = None,
    ) -> TaskSpec:
        self.taskSpec.lastFiredAt = time.time()
        self.taskSpec.fireCount += 1
        return self.taskSpec

    def RunAsync(
        self,
        onFinished: Optional["TaskDoneCallback"] = None,
    ) -> "TaskHandle[ScheduleTask]":
        from .cronScheduler import _DEFAULT_CRON_SCHEDULER

        return _DEFAULT_CRON_SCHEDULER.Schedule(self, onFinished=onFinished)
