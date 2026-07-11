"""CronScheduler —— 基于 croniter 的秒级 cron 调度器。"""

from __future__ import annotations

import asyncio
import hashlib
import time
from datetime import datetime
from typing import Callable, TypeVar

from croniter import croniter

from common.logger import Logger
from task.core import BaseScheduler, ETaskStatus, TaskT
from task.core.taskHandle import TaskDoneCallback, TaskHandle

from .taskSpec import TaskSpec

JitterCallback = Callable[[], None]
TCronTask = TypeVar("TCronTask", bound=TaskT[TaskSpec])


class CronScheduler(BaseScheduler):
    """基于 croniter 的 cron 调度器。"""

    def __init__(self) -> None:
        self._jobs: dict[str, tuple[str, JitterCallback, datetime]] = {}
        self._handleToJobId: dict[int, str] = {}
        self._tickerTask: asyncio.Task | None = None
        self._running: bool = False

    # ---- 生命周期 ----

    def EnsureStarted(self) -> None:
        """若尚未运行则启动 ticker（同步，要求当前有 running loop）。"""
        if self._running:
            return
        self._running = True
        self._tickerTask = asyncio.create_task(self._TickAsync())

    async def StopAsync(self) -> None:
        """停止调度器。"""
        self._running = False
        if self._tickerTask is not None:
            self._tickerTask.cancel()
            try:
                await self._tickerTask
            except asyncio.CancelledError:
                pass
            self._tickerTask = None

    # ---- Job 管理 ----

    def AddJob(self, expression: str, callback: JitterCallback) -> str:
        """注册一个 cron job。"""
        cron = croniter(expression, datetime.now())
        nextFire = cron.get_next(datetime)
        jobId = self._GenerateJobId()
        self._jobs[jobId] = (expression, callback, nextFire)
        return jobId

    def RemoveJob(self, jobId: str) -> bool:
        """按 jobId 删除 job。"""
        if jobId in self._jobs:
            del self._jobs[jobId]
            return True
        return False

    def Clear(self) -> None:
        """清空所有 job。"""
        self._jobs.clear()
        self._handleToJobId.clear()

    def Schedule(
        self,
        task: TCronTask,
        onFinished: TaskDoneCallback | None = None,
    ) -> TaskHandle[TCronTask]:
        """按 task.taskSpec.expression 调度任务，到期后执行 ExecuteAsync。"""
        self._EnsureEventLoop()
        expression = task.taskSpec.expression
        handle = self._CreateHandle(task, onFinished)
        firedFuture: asyncio.Future[None] = asyncio.get_running_loop().create_future()

        def OnFire() -> None:
            if task.info.status != ETaskStatus.RUNNING:
                return
            jobId = self._handleToJobId.pop(task.info.taskId, "")
            if jobId:
                self.RemoveJob(jobId)
            if not firedFuture.done():
                firedFuture.set_result(None)

        jobId = self.AddJob(expression, OnFire)
        self._handleToJobId[task.info.taskId] = jobId
        handle.asyncioTask = asyncio.create_task(self._WaitAndExecuteAsync(handle, firedFuture))
        self.EnsureStarted()
        return handle

    def ListJobs(self) -> list[dict]:
        """列出所有活跃 job。"""
        result: list[dict] = []
        for jobId, (expression, _, nextFire) in self._jobs.items():
            result.append({
                "jobId": jobId,
                "expression": expression,
                "nextFire": nextFire.isoformat(),
            })
        return result

    # ---- 内部 ----

    async def _TickAsync(self) -> None:
        """每秒扫描到期 job 并触发。"""
        while self._running:
            try:
                now = datetime.now()
                for jobId, (expression, callback, nextFire) in list(self._jobs.items()):
                    if now >= nextFire:
                        jitterSeconds = self._GetJitter(jobId, expression)
                        if jitterSeconds > 0:
                            await asyncio.sleep(jitterSeconds)
                        try:
                            callback()
                        except Exception:
                            Logger.Error(f"CronScheduler: job {jobId} callback failed")
                        if jobId in self._jobs:
                            cron = croniter(expression, datetime.now())
                            self._jobs[jobId] = (
                                expression,
                                callback,
                                cron.get_next(datetime),
                            )
            except Exception:
                Logger.Error("CronScheduler: tick error")
            await asyncio.sleep(1)

    async def _WaitAndExecuteAsync(
        self,
        handle: TaskHandle,
        firedFuture: asyncio.Future[None],
    ) -> None:
        await firedFuture
        await self._ExecuteCoreAsync(handle)
        self._NotifyFinished(handle)

    def _OnHandleCancel(self, handle: TaskHandle) -> None:
        task = handle.task
        jobId = self._handleToJobId.pop(task.info.taskId, "")
        if jobId:
            self.RemoveJob(jobId)

    def _GetJitter(self, jobId: str, expression: str) -> float:
        """根据 jobId 派生确定性 jitter 偏移（秒）。"""
        hashVal = int(hashlib.md5(jobId.encode()).hexdigest()[:8], 16)
        cron = croniter(expression, datetime.now())
        t1 = cron.get_next(datetime)
        t2 = cron.get_next(datetime)
        interval = (t2 - t1).total_seconds()
        if interval <= 0:
            return 0.0
        maxJitter = min(1800.0, interval / 2)
        return (hashVal % int(maxJitter)) if maxJitter > 0 else 0.0

    @staticmethod
    def _GenerateJobId() -> str:
        """生成 8 字符 jobId。"""
        return hashlib.md5(str(time.time_ns()).encode()).hexdigest()[:8]


_DEFAULT_CRON_SCHEDULER = CronScheduler()

