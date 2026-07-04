"""TodoWrite 工具 —— 创建和管理任务列表。"""

from __future__ import annotations

from agent.component.contex.eContextLodLevel import EContextLodLevel

from ..baseTool import BaseTool
from ..eToolCategory import EToolCategory
from ..toolResult import ToolResult
from ..toolComponent import ToolComponent


@ToolComponent.Register
class TodoWriteTool(BaseTool):
    """创建和管理任务列表，用于跟踪复杂多步骤任务。

    LLM 自主拆解任务 → 逐项标记状态推进。
    框架不干预拆解逻辑，仅提供工具接口。
    """

    name: str = "todoWrite"
    description: str = "Create and manage a task list for complex multi-step tasks"
    resultLodLevel = EContextLodLevel.SUMMARIZABLE
    category: EToolCategory = EToolCategory.AGENT
    parameters: dict = {
        "type": "object",
        "properties": {
            "merge": {
                "type": "boolean",
                "description": "true=merge by id, false=replace all"
            },
            "todos": {
                "type": "array",
                "description": "Todo items array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": "Unique id"
                        },
                        "content": {
                            "type": "string",
                            "description": "Task description"
                        },
                        "status": {
                            "type": "string",
                            "enum": ["PENDING", "IN_PROGRESS", "COMPLETE", "CANCELLED"],
                            "description": "Status: PENDING, IN_PROGRESS, COMPLETE, CANCELLED"
                        },
                    },
                    "required": ["id", "content", "status"],
                },
            },
        },
        "required": ["merge", "todos"],
    }

    def _Invoke(self, merge: bool, todos: list[dict]) -> ToolResult:
        """执行 TodoWrite 操作。

        验证输入格式并返回格式化的清单摘要。
        实际状态由前端根据 tool call 事件渲染，此处仅做校验和确认。
        """
        if not isinstance(todos, list):
            return ToolResult.Fail("'todos' must be a list", toolName=self.name)

        validStatuses = {"PENDING", "IN_PROGRESS", "COMPLETE", "CANCELLED"}
        for i, item in enumerate(todos):
            if not isinstance(item, dict):
                return ToolResult.Fail(
                    f"todos[{i}] must be an object", toolName=self.name,
                )
            missing = [f for f in ("id", "content", "status") if f not in item]
            if missing:
                return ToolResult.Fail(
                    f"todos[{i}] missing required field: {', '.join(missing)}",
                    toolName=self.name,
                )
            if item["status"] not in validStatuses:
                return ToolResult.Fail(
                    f"todos[{i}].status '{item['status']}' invalid, "
                    f"must be one of: {', '.join(sorted(validStatuses))}",
                    toolName=self.name,
                )

        # 格式化摘要
        mode = "Merged" if merge else "Created"
        lines = [f"{mode} task list with {len(todos)} item(s):"]
        statusIcons = {
            "PENDING": "   ",
            "IN_PROGRESS": "-> ",
            "COMPLETE": "[x]",
            "CANCELLED": "[-]",
        }
        for item in todos:
            icon = statusIcons.get(item["status"], " ? ")
            lines.append(f"  {icon} [{item['id']}] {item['content']}")

        return ToolResult.Ok("\n".join(lines), toolName=self.name)
