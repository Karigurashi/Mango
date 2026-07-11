"""
并行报数 Demo —— 4 个 SimpleAgent 并行报数，通过 EventBus 观察 FLOW_DONE 汇总结果。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parent)
sys.path.insert(0, PROJECT_ROOT)

import task.workflow.nodes  # noqa

from task.workflow.core.workflowEdge import EEdgeType
from task.workflow.nodes.action import BeginNode, SimpleAgentNode
from task.workflow.nodes.composite import ParallelNode

from task.workflow.core.eTaskProgressKind import ETaskProgressKind
from task.workflow.core.taskProgressData import TaskProgressData


AGENT_NAMES = ["报数员A", "报数员B", "报数员C", "报数员D"]


def _OnEvent(data: TaskProgressData) -> None:
    """Workflow 进度监听器：打印所有事件并验证 FLOW_DONE 汇总。"""
    wfId = 0
    kind = data.kind

    if kind == ETaskProgressKind.FLOW_START:
        print(f"[WF{wfId}] === FLOW_START ===")

    elif kind == ETaskProgressKind.FLOW_DONE:
        print(f"\n[WF{wfId}] === FLOW_DONE ===")
        if data.message:
            print(f"[WF{wfId}] [汇总消息]:\n{data.message}")
        else:
            print(f"[WF{wfId}] [WARNING] FLOW_DONE 消息为空！")

    elif kind == ETaskProgressKind.FLOW_CANCEL:
        print(f"[WF{wfId}] === FLOW_CANCEL ===")

    elif kind == ETaskProgressKind.NODE_STATUS:
        print(f"[WF{wfId}] [节点{data.nodeId}] {data.status or 'UNKNOWN'}")

    elif kind == ETaskProgressKind.AI_CONTENT:
        print(f"[WF{wfId}] [AI 内容]:\n{data.message}")


async def main():
    from task.workflow.workflow import Workflow

    wf = Workflow("并行报数Demo")
    wf.AddProgressListener(_OnEvent)

    # 节点 1: BeginNode
    wf.graph.AddNode(1, BeginNode(), 0, 0)

    # 节点 2: ParallelNode（并行容器）
    wf.graph.AddNode(2, ParallelNode(name="并行报数"), 150, 0)

    # 节点 3-6: 4 个 SimpleAgentNode（并行报数员）
    for i, name in enumerate(AGENT_NAMES):
        nodeId = 3 + i
        wf.graph.AddNode(nodeId, SimpleAgentNode(
            name=name,
            ModelName="deepseek-mid",
            SystemPrompt=(
                f"你是{name}，负责报数。"
                "请严格按以下格式输出，每行一个数字，不要输出任何其他内容：\n"
                "1\n2\n3"
            ),
            Temperature=0.3,
        ), 300, 100 + i * 80)

    # BeginNode -> ParallelNode（OUT 边）
    wf.graph.AddEdge(1, 2, EEdgeType.OUT)

    # ParallelNode -> 4 个 SimpleAgentNode（SUB_NODE 边）
    for i in range(4):
        wf.graph.AddEdge(2, 3 + i, EEdgeType.CHILD)

    # Workflow 本身可等待，内部使用共享调度器执行
    print("=" * 40)
    await wf
    print("=" * 40)
    print(f"\n[OK] 工作流状态: {wf.info.status.name}, 摘要: {wf.summary}")


if __name__ == "__main__":
    asyncio.run(main())
