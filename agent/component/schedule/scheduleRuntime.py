"""ScheduleRuntime —— 定时定义到运行任务的桥接层。"""

from __future__ import annotations

import asyncio
from typing import Callable, Optional

from task.core.taskHandle import TaskHandle
from task.schedule.scheduleTask import ScheduleTask
from task.schedule.taskSpec import TaskSpec

from .scheduleRegistry import ScheduleRegistry

SubmitTaskCallback = Callable[[ScheduleTask], TaskHandle[ScheduleTask]]


class ScheduleRuntime:
    """管理 TaskSpec 的持久化，并提交自调度的 ScheduleTask。"""

    def __init__(self, tasksDir: str, submitTask: SubmitTaskCallback) -> None:
        self._registry = ScheduleRegistry(tasksDir)
        self._submitTask = submitTask
        self._taskIdToSpecId: dict[int, int] = {}
        self._specToTaskId: dict[int, int] = {}
        self._handles: dict[int, TaskHandle[ScheduleTask]] = {}
        self._tasks: dict[int, ScheduleTask] = {}

    def Load(self) -> None:
        """从持久化载入定义，等待事件循环就绪后挂载。"""
        self._registry.Load()

    def TryArmPending(self) -> None:
        """事件循环就绪时，为 pending specs 启动 ScheduleTask。"""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return

        for spec in self._registry.DrainPending():
            self._StartTask(spec)

    def Clear(self) -> None:
        """清空运行时任务和注册表。"""
        for handle in list(self._handles.values()):
            handle.Cancel()
        self._registry.Clear()
        self._taskIdToSpecId.clear()
        self._specToTaskId.clear()
        self._handles.clear()
        self._tasks.clear()

    def GetSpec(self, specId: int) -> Optional[TaskSpec]:
        return self._registry.GetSpec(specId)

    def GetSpecId(self, taskId: int) -> Optional[int]:
        return self._taskIdToSpecId.get(taskId)

    def ListSpecs(self) -> list[TaskSpec]:
        return self._registry.ListSpecs()

    def ListTasks(self) -> list[ScheduleTask]:
        return list(self._tasks.values())

    def CreateAgentWake(
        self,
        name: str,
        expression: str,
        prompt: str,
    ) -> TaskSpec:
        """创建并挂载一个 AgentWake 定时定义。"""
        self.TryArmPending()
        spec = self._registry.CreateAgentWake(
            name=name,
            expression=expression,
            prompt=prompt,
        )
        self._StartTask(spec)
        return spec

    def Delete(self, specId: int) -> bool:
        """删除定义并取消对应 ScheduleTask。"""
        self.TryArmPending()
        taskId = self._specToTaskId.pop(specId, 0)
        if taskId:
            handle = self._handles.pop(taskId, None)
            if handle is not None:
                handle.Cancel()
            self._tasks.pop(taskId, None)
            self._taskIdToSpecId.pop(taskId, None)

        return self._registry.Remove(specId)

    def ForgetRun(self, taskId: int) -> None:
        """移除已完成任务并为仍存在的 spec 启动下一轮。"""
        specId = self._taskIdToSpecId.pop(taskId, None)
        self._handles.pop(taskId, None)
        task = self._tasks.pop(taskId, None)
        if task is not None:
            self._registry.SyncFireStats(
                task.taskSpec.specId,
                task.taskSpec.lastFiredAt,
                task.taskSpec.fireCount,
            )
        if specId is None:
            return
        self._specToTaskId.pop(specId, None)
        spec = self._registry.GetSpec(specId)
        if spec is not None:
            self._StartTask(spec)

    def _StartTask(self, spec: TaskSpec) -> None:
        if spec.specId in self._specToTaskId:
            return
        task = ScheduleTask(spec)
        handle = self._submitTask(task)
        self._tasks[task.info.taskId] = task
        self._handles[task.info.taskId] = handle
        self._taskIdToSpecId[task.info.taskId] = spec.specId
        self._specToTaskId[spec.specId] = task.info.taskId
