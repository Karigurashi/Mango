"""ScheduleRegistry —— 定时任务定义的注册表：创建 / 删除 / 恢复 / 落盘。"""

from __future__ import annotations

import os
import tempfile
import time
from datetime import datetime
from typing import Optional

from croniter import croniter

from common import SerializeUtil
from task.schedule.taskSpec import TaskSpec

SCHEDULES_FILENAME = "schedules.json"


class ScheduleRegistry:
    """维护 TaskSpec 集合，负责 JSON 持久化。"""

    def __init__(self, tasksDir: str) -> None:
        self._tasksDir = tasksDir
        self._filePath = os.path.join(tasksDir, SCHEDULES_FILENAME)
        self._specs: dict[int, TaskSpec] = {}
        self._pendingRestore: list[TaskSpec] = []
        self._nextSpecId: int = 1

    def GetSpec(self, specId: int) -> Optional[TaskSpec]:
        return self._specs.get(specId)

    def ListSpecs(self) -> list[TaskSpec]:
        return list(self._specs.values())

    def Load(self) -> None:
        """从 JSON 载入定义到 pending，待事件循环就绪后再物化。"""
        self._pendingRestore.clear()
        maxId = 0
        for spec in self._LoadAll():
            if spec.specId <= 0 or not spec.expression:
                continue
            self._pendingRestore.append(spec)
            self._specs[spec.specId] = spec
            if spec.specId > maxId:
                maxId = spec.specId
        self._nextSpecId = maxId + 1

    def CreateAgentWake(
        self,
        name: str,
        expression: str,
        prompt: str,
    ) -> TaskSpec:
        """校验 cron 并创建 Spec。"""
        croniter(expression, datetime.now())

        specId = self._AllocSpecId()
        spec = TaskSpec(
            specId=specId,
            name=name or "AgentWake",
            expression=expression,
            prompt=prompt,
            createdAt=time.time(),
        )
        self._specs[spec.specId] = spec
        self.Persist()
        return spec

    def Remove(self, specId: int) -> bool:
        """删除定义并落盘。"""
        before = len(self._pendingRestore)
        self._pendingRestore = [s for s in self._pendingRestore if s.specId != specId]
        removedPending = len(self._pendingRestore) < before
        removedSpec = self._specs.pop(specId, None) is not None

        found = removedSpec or removedPending
        if not found:
            return False

        self.Persist()
        return True

    def DrainPending(self) -> list[TaskSpec]:
        """取出待挂载的 specs。"""
        pending = self._pendingRestore[:]
        self._pendingRestore.clear()
        return pending

    def SyncFireStats(self, specId: int, lastFiredAt: float, fireCount: int) -> None:
        """用 fire 统计回写 Spec 并落盘。"""
        spec = self._specs.get(specId)
        if spec is None:
            return
        spec.lastFiredAt = lastFiredAt
        spec.fireCount = fireCount
        self.Persist()

    def Persist(self) -> None:
        byId = {s.specId: s for s in self._specs.values()}
        for spec in self._pendingRestore:
            byId[spec.specId] = spec
        self._SaveAll(list(byId.values()))

    def Clear(self) -> None:
        self._specs.clear()
        self._pendingRestore.clear()
        self._nextSpecId = 1

    def _AllocSpecId(self) -> int:
        specId = self._nextSpecId
        self._nextSpecId += 1
        return specId

    def _LoadAll(self) -> list[TaskSpec]:
        """加载全部 TaskSpec；文件不存在返回空列表。"""
        if not os.path.isfile(self._filePath):
            return []
        with open(self._filePath, "r", encoding="utf-8") as f:
            data = SerializeUtil.FromJson(f.read())
        return [SerializeUtil.FromDict(item, TaskSpec) for item in data["tasks"]]

    def _SaveAll(self, specs: list[TaskSpec]) -> None:
        """原子覆盖写入全部 TaskSpec。"""
        os.makedirs(self._tasksDir, exist_ok=True)
        payload = {
            "version": 1,
            "tasks": [SerializeUtil.ToDict(s) for s in specs],
        }
        content = SerializeUtil.ToJson(payload, indent=2)
        dirName = os.path.dirname(self._filePath) or "."
        fd, tmpPath = tempfile.mkstemp(dir=dirName, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmpPath, self._filePath)
        except Exception:
            if os.path.isfile(tmpPath):
                os.remove(tmpPath)
            raise
