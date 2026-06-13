"""工作流断点管理器 —— 将 WorkflowContext 执行进度持久化为 Markdown 检查点。

停电/主动断开后可从最近的 checkpoint 恢复执行，跳过已完成节点。

Checkpoint 文件格式（Markdown + YAML frontmatter）::

    ---
    workflow: "数据处理流水线"
    session_id: "a1b2c3d4"
    status: CHECKPOINTED
    created: 2026-06-08T14:32:00
    updated: 2026-06-08T15:47:00
    completed_nodes: "1,2,3"
    current_node: 4
    execution_round: 12
    ---

    # Checkpoint: 数据处理流水线

    ## Completed Nodes (3/5)
    - Node 1: Action/BeginPlay — COMPLETED
    - Node 2: Action/LLMClientCall — COMPLETED
    - Node 3: Composite/Parallel — COMPLETED

    ## Pending Nodes
    - Node 4: Action/LLMClientCall — PENDING
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Optional, TYPE_CHECKING

from common.logger import Logger

if TYPE_CHECKING:
    from .memoryStore import MemoryStore


class CheckpointManager:
    """工作流断点管理器，负责保存和恢复 WorkflowContext 执行进度。

    使用方式::

        store = MemoryStore()
        cpm = CheckpointManager(store)

        # 保存断点
        cpm.Save("my-workflow", "session-123", completedNodes=[1,2,3],
                  currentNode=4, executionRound=12, contextData={"var.x": 42})

        # 恢复断点
        cp = cpm.LoadLatest("my-workflow")
        if cp:
            print(cp.completedNodes)  # [1, 2, 3]
    """

    def __init__(self, store: "MemoryStore") -> None:
        self._store = store

    # ---- 保存 ----

    def Save(
        self,
        workflowName: str,
        sessionId: str,
        completedNodes: list[int],
        currentNode: int = 0,
        executionRound: int = 0,
        contextData: dict[str, Any] | None = None,
        nodeDetails: list[dict[str, Any]] | None = None,
    ) -> str | None:
        """保存检查点，返回文件路径。

        Args:
            workflowName: 工作流名称。
            sessionId: 当前会话 ID。
            completedNodes: 已完成节点 ID 列表。
            currentNode: 当前正在执行的节点 ID（0 表示无）。
            executionRound: 当前执行轮次。
            contextData: 需持久化的上下文 KV 数据。
            nodeDetails: 节点执行详情列表，每项含 nodeId/type/status/outputKey。
        """
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        safeName = self._SafeFileName(workflowName)

        # 构建 frontmatter
        meta = {
            "workflow": workflowName,
            "session_id": sessionId,
            "status": "CHECKPOINTED",
            "created": now,
            "updated": now,
            "completed_nodes": ",".join(str(n) for n in completedNodes),
            "current_node": str(currentNode),
            "execution_round": str(executionRound),
        }

        # 构建正文
        bodyLines = [
            f"# Checkpoint: {workflowName}",
            "",
            f"**Updated**: {now}",
            f"**Completed**: {len(completedNodes)} node(s) | **Round**: {executionRound}",
            "",
        ]

        if nodeDetails:
            bodyLines.append("## Completed Nodes")
            for nd in nodeDetails:
                nodeId = nd.get("nodeId", "?")
                nodeType = nd.get("type", "?")
                status = nd.get("status", "COMPLETED")
                bodyLines.append(f"- Node {nodeId}: {nodeType} — **{status}**")

        if currentNode:
            bodyLines.append(f"\n## Current Node\n- Node {currentNode} — PENDING")

        if contextData:
            bodyLines.append("\n## Context Data (KV)")
            for key, value in contextData.items():
                valStr = json.dumps(value, ensure_ascii=False)
                if len(valStr) > 200:
                    valStr = valStr[:200] + "..."
                bodyLines.append(f"- `{key}`: {valStr}")

        frontmatter = self._store.BuildFrontmatter(meta)
        content = frontmatter + "\n".join(bodyLines)

        # 写入 checkpoints/{workflowName}/{sessionId}.md
        checkpointDir = os.path.join(self._store.CheckpointsDir, safeName)
        os.makedirs(checkpointDir, exist_ok=True)
        filePath = os.path.join(checkpointDir, f"{sessionId}.md")

        if self._store.WriteFile(filePath, content):
            # 同步更新 latest.md
            latestPath = os.path.join(checkpointDir, "latest.md")
            self._store.WriteFile(latestPath, content)
            Logger.Info(
                f"CheckpointManager: saved [{workflowName}] "
                f"completed={len(completedNodes)} round={executionRound}"
            )
            return filePath

        return None

    # ---- 加载 ----

    def LoadLatest(self, workflowName: str) -> dict[str, Any] | None:
        """加载工作流的最新检查点。

        Returns:
            包含 checkpoint 数据的字典，无检查点时返回 None。
            Keys: workflow, sessionId, status, completedNodes(list[int]),
                  currentNode(int), executionRound(int), contextData(dict),
                  nodeDetails(list[dict]).
        """
        safeName = self._SafeFileName(workflowName)
        latestPath = os.path.join(self._store.CheckpointsDir, safeName, "latest.md")

        raw = self._store.ReadFile(latestPath)
        if raw is None:
            return None

        return self._ParseCheckpoint(raw)

    def LoadBySession(self, workflowName: str, sessionId: str) -> dict[str, Any] | None:
        """加载指定会话的检查点。"""
        safeName = self._SafeFileName(workflowName)
        filePath = os.path.join(
            self._store.CheckpointsDir, safeName, f"{sessionId}.md"
        )

        raw = self._store.ReadFile(filePath)
        if raw is None:
            return None

        return self._ParseCheckpoint(raw)

    def ListCheckpoints(self, workflowName: str) -> list[str]:
        """列出某工作流的所有检查点文件（session ID 列表）。"""
        safeName = self._SafeFileName(workflowName)
        checkpointDir = os.path.join(self._store.CheckpointsDir, safeName)
        files = self._store.ListFiles(checkpointDir, ".md")
        return [f[:-3] for f in files if f != "latest.md"]

    # ---- 删除 ----

    def DeleteCheckpoint(self, workflowName: str, sessionId: str) -> bool:
        """删除指定检查点。"""
        safeName = self._SafeFileName(workflowName)
        filePath = os.path.join(
            self._store.CheckpointsDir, safeName, f"{sessionId}.md"
        )
        try:
            if os.path.isfile(filePath):
                os.remove(filePath)
                return True
            return False
        except OSError:
            return False

    def ClearAll(self, workflowName: str) -> int:
        """清空某工作流的所有检查点，返回删除数量。"""
        safeName = self._SafeFileName(workflowName)
        checkpointDir = os.path.join(self._store.CheckpointsDir, safeName)
        count = 0
        try:
            for f in os.listdir(checkpointDir):
                if f.endswith(".md"):
                    os.remove(os.path.join(checkpointDir, f))
                    count += 1
        except OSError:
            pass
        return count

    # ---- 内部 ----

    @staticmethod
    def _SafeFileName(name: str) -> str:
        """将工作流名转为安全的文件名。"""
        import re
        return re.sub(r"[^\w\-.]", "_", name)

    def _ParseCheckpoint(self, raw: str) -> dict[str, Any] | None:
        """从 Markdown 原始内容解析检查点数据。"""
        meta, _body = self._store.ParseFrontmatter(raw)
        if not meta:
            return None

        # 解析 completed_nodes → list[int]
        completedStr = meta.get("completed_nodes", "")
        completedNodes = [
            int(x.strip()) for x in completedStr.split(",") if x.strip().isdigit()
        ]

        # 解析 currentNode
        currentNode = int(meta.get("current_node", "0"))

        # 解析 executionRound
        executionRound = int(meta.get("execution_round", "0"))

        return {
            "workflow": meta.get("workflow", ""),
            "sessionId": meta.get("session_id", ""),
            "status": meta.get("status", "CHECKPOINTED"),
            "completedNodes": completedNodes,
            "currentNode": currentNode,
            "executionRound": executionRound,
            "rawMeta": meta,
            "rawBody": _body,
        }

    def __repr__(self) -> str:
        return f"CheckpointManager(baseDir={self._store.CheckpointsDir!r})"
