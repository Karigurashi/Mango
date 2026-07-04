"""
并行对话 Demo — 提问者与回答者顺序执行。
"""

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parent)
sys.path.insert(0, PROJECT_ROOT)

import workflow.nodes  # noqa

from workflow.core.eEdgeType import EEdgeType
from workflow.core.workflowStreamEvent import EStreamEventType
from workflow.nodes.action import BeginPlayNode, AgentNode, SimpleAgentNode


async def main():
    from workflow.workflow import Workflow
    wf = Workflow("并行对话Demo")

    wf.graph \
        .AddNode(1, BeginPlayNode(), 0, 0) \
        .AddNode(2, AgentNode(
            name="提问者",
            ModelName="deepseek-mid",
            SystemPrompt=(
                "你是一个富有好奇心的提问专家。"
                "根据上一轮的回答，提出一个更深层次的追问。"
                "如果这是第一轮，请提出一个有趣的开放性问题。"
                "只需要提出问题，不要发表观点或回答问题。"
            ),
            UserMessage="请提出一个开放性问题",
            Temperature=0.9,
        ), 200, 0) \
        .AddNode(3, SimpleAgentNode(
            name="回答者",
            ModelName="deepseek-mid",
            SystemPrompt=(
                "你是一个知识渊博的思考者。"
                "请对收到的问题进行深入回答。"
                "回答要简洁有力，100-200字。"
            ),
            Temperature=0.8,
        ), 400, 0)

    # 主流程边
    wf.graph \
        .AddEdge(1, 2, EEdgeType.OUT) \
        .AddEdge(2, 3, EEdgeType.OUT)

    wf.eventBus.AddListener(_OnEvent)

    await wf.ExecuteAsync()


if __name__ == "__main__":
    asyncio.run(main())
