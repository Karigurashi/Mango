"""JSON 工作流加载示例 —— 演示从 Workflow.json 文件加载并执行多节点工作流。

本示例执行一个多步骤工作流：
  BeginPlay → LLM(数学计算) → Delay(2s) → LLM(天气助手)
"""

import asyncio
import json
import os
import sys

# 将项目根目录加入 sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from workflow import Workflow


async def exampleWorkflowFromJson():
    """加载 Workflow.json 并执行，通过流式回调捕获每个 LLM 节点的输出。"""
    print("=" * 40)
    print("Workflow.json 工作流执行示例")
    print("=" * 40)

    # 1. 加载 JSON 文件
    jsonPath = os.path.join(os.path.dirname(__file__), "Workflow.json")
    with open(jsonPath, "r", encoding="utf-8") as f:
        jsonData = json.load(f)

    print(f"工作流: {jsonData['name']}  |  "
          f"节点: {len(jsonData['nodes'])}  |  "
          f"边: {len(jsonData['edges'])}")

    # 打印节点结构
    for node in jsonData["nodes"]:
        name = node.get("name", "")
        label = f" ({name})" if name else ""
        print(f"  [{node['id']}] {node['type']}{label}")

    # 2. 反序列化
    wf = Workflow.FromJson(jsonData)

    # 3. 流式回调 —— 捕获每个 LLM 节点的增量输出
    nodeOutputs: dict[int, dict] = {}

    async def onNodeStream(nodeId: int, eventType: str, data: dict):
        if nodeId not in nodeOutputs:
            nodeOutputs[nodeId] = {"content": "", "reasoning": ""}
        out = nodeOutputs[nodeId]
        if eventType == "content":
            out["content"] += data.get("text", "")
        elif eventType == "thinking":
            out["reasoning"] += data.get("text", "")

    # 4. 执行
    print("\n执行中...")
    ctx = await wf.ExecuteAsync(onNodeStream=onNodeStream)

    # 5. 输出结果
    print("\n各 LLM 节点输出:")
    for nodeId, out in sorted(nodeOutputs.items()):
        node = wf.graph.GetNode(nodeId)
        nodeName = node.name if node else f"Node{nodeId}"
        print(f"  [{nodeId}] {nodeName}: {out['content'][:120]}")
        if out["reasoning"]:
            print(f"       推理: {out['reasoning'][:100]}...")

    # 验证
    totalContent = sum(bool(o["content"]) for o in nodeOutputs.values())
    assert totalContent > 0, "LLM 节点未返回回复!"
    print("\n✓ 通过")


async def main():
    await exampleWorkflowFromJson()


if __name__ == "__main__":
    asyncio.run(main())
