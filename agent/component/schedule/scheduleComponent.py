"""ScheduleComponent —— Agent 侧定时任务组件。"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Optional

from agent.component.data.dataComponent import DataComponent
from agent.component.data.eAgentState import EAgentState
from agent.component.eventBus.agentStreamEvent import EAgentStreamEventType
from agent.core.baseComponent import IComponent
from task.core import ETaskStatus
from task.core.taskHandle import TaskHandle
from task.schedule import ScheduleTask, TaskSpec

from .scheduleRuntime import ScheduleRuntime

if TYPE_CHECKING:
    from agent.component.eventBus.agentStreamEvent import AgentStreamEvent
    from agent.core.baseAgent import BaseAgent


class ScheduleComponent(IComponent):
    """管理 ScheduleTask 的定义、运行、取消和回注。"""

    def OnInitialize(self, agent: BaseAgent) -> None:
        self._agent: BaseAgent = agent
        self._handles: dict[int, TaskHandle[ScheduleTask]] = {}
        self._tasks: dict[int, ScheduleTask] = {}
        self._pendingInjects: list[int] = []

        dataComp = agent.GetComponent(DataComponent)
        self._schedule = ScheduleRuntime(dataComp.config.tasksDir, self._SubmitScheduledTask)
        self._schedule.Load()

        from agent.component.eventBus.eventBusComponent import EventBusComponent
        self._eventBus = agent.GetComponent(EventBusComponent)
        self._eventBus.AddListener(self._OnAgentEvent)

        self.TryArmPending()

    def OnDestroy(self) -> None:
        self._eventBus.RemoveListener(self._OnAgentEvent)
        self._handles.clear()
        self._tasks.clear()
        self._pendingInjects.clear()
        self._schedule.Clear()

    def CreateScheduleTask(
        self,
        name: str,
        expression: str,
        prompt: str,
    ) -> TaskSpec:
        """创建定时任务：Registry 落盘 + ScheduleTask 后台等待 cron。"""
        self.TryArmPending()
        return self._schedule.CreateAgentWake(
            name=name,
            expression=expression,
            prompt=prompt,
        )

    def DeleteTask(self, specId: int) -> bool:
        """按 specId 取消运行任务并删除持久化定义。"""
        self.TryArmPending()
        staleTaskIds = [
            taskId
            for taskId, task in self._tasks.items()
            if task.taskSpec.specId == specId
        ]
        if not self._schedule.Delete(specId):
            return False
        for taskId in staleTaskIds:
            if taskId in self._pendingInjects:
                self._pendingInjects.remove(taskId)
            handle = self._handles.pop(taskId, None)
            if handle is not None:
                handle.Cancel()
            self._tasks.pop(taskId, None)
        return True

    def Cancel(self, taskId: int) -> bool:
        """取消指定定时任务；若有关联 spec 一并删除持久化。"""
        task = self._tasks.get(taskId)
        if task is not None and task.taskSpec.specId:
            return self.DeleteTask(task.taskSpec.specId)
        specId = self._schedule.GetSpecId(taskId)
        if specId:
            return self.DeleteTask(specId)
        return False

    def GetSpec(self, specId: int) -> Optional[TaskSpec]:
        return self._schedule.GetSpec(specId)

    def ListTasks(self) -> list[ScheduleTask]:
        return self._schedule.ListTasks()

    def ListSpecs(self) -> list[TaskSpec]:
        return self._schedule.ListSpecs()

    def TryArmPending(self) -> None:
        """事件循环就绪时，恢复 pending specs。"""
        self._schedule.TryArmPending()

    def _SubmitScheduledTask(self, task: ScheduleTask) -> TaskHandle[ScheduleTask]:
        self._tasks[task.info.taskId] = task
        handle = task.RunAsync(self._OnTaskFinished)
        self._handles[task.info.taskId] = handle
        return handle

    def _OnTaskFinished(self, handle: TaskHandle) -> None:
        task = self._tasks.get(handle.task.info.taskId)
        if task is None:
            return
        self._HandleScheduledFinished(task)

    def _HandleScheduledFinished(self, task: ScheduleTask) -> None:
        taskId = task.info.taskId
        if task.info.status == ETaskStatus.CANCELLED:
            if taskId in self._pendingInjects:
                self._pendingInjects.remove(taskId)
            return

        if task.info.status != ETaskStatus.COMPLETED:
            return

        self._schedule.ForgetRun(taskId)
        if self._IsAgentBusy():
            self._pendingInjects.append(taskId)
        else:
            self._InjectResult(taskId)

    def _OnAgentEvent(self, event: AgentStreamEvent) -> None:
        if event.eventType == EAgentStreamEventType.DONE:
            self._FlushPendingInjects()

    def _FlushPendingInjects(self) -> None:
        pending = self._pendingInjects[:]
        self._pendingInjects.clear()
        for taskId in pending:
            self._InjectResult(taskId)

    def _InjectResult(self, taskId: int) -> None:
        content = self._FormatInjectContent(taskId)
        if not content:
            return
        self._RunAgentWithContent(content)
        self._CleanupCompletedRun(taskId)

    def _FormatInjectContent(self, taskId: int) -> str | None:
        task = self._tasks.get(taskId)
        if task is None or not task.taskSpec.prompt:
            return None
        name = task.taskSpec.name or "Scheduled"
        return f"[Scheduled:{name}]\n{task.taskSpec.prompt}"

    def _CleanupCompletedRun(self, taskId: int) -> None:
        self._tasks.pop(taskId, None)
        self._handles.pop(taskId, None)

    def _RunAgentWithContent(self, content: str) -> None:
        runStream = getattr(self._agent, "RunStreamAsync", None)
        if runStream is None:
            return
        asyncio.create_task(runStream(content))

    def _IsAgentBusy(self) -> bool:
        dataComp = self._agent.GetComponent(DataComponent)
        return dataComp.state in (
            EAgentState.THINKING,
            EAgentState.ACTING,
            EAgentState.WAITING_USER,
        )
