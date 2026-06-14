"""TodoWrite 工具 —— AI 自主拆解复杂任务为清单、逐项标记状态推进。

对标 Claude Code 的 TodoWrite 工具。拆解、标记、推进全部由 LLM 决策，
Agent 框架只需注册此工具并注入使用说明到 System Prompt。

使用模式::

    # 初始化清单
    todo_write(merge=false, todos=[
        {"id": "1", "content": "分析需求", "status": "in_progress"},
        {"id": "2", "content": "设计方案", "status": "pending"},
        {"id": "3", "content": "实现代码", "status": "pending"},
    ])

    # 更新状态（merge=true）
    todo_write(merge=true, todos=[
        {"id": "1", "content": "分析需求", "status": "completed"},
        {"id": "2", "content": "设计方案", "status": "in_progress"},
    ])
"""

from __future__ import annotations

from ..baseTool import BaseTool
from ..eToolCategory import EToolCategory
from ..toolResult import ToolResult
from ..toolComponent import ToolComponent


@ToolComponent.Register
class TodoWriteTool(BaseTool):
    """创建和管理任务清单，用于追踪复杂多步任务的进度。

    LLM 自主拆解任务 → 逐项标记 pending/in_progress/completed/cancelled。
    框架不干预拆解逻辑，仅提供工具接口。
    """

    name: str = "todo_write"
    description: str = (
        "Create and manage a structured task list to track progress on complex, "
        "multi-step tasks. Use this proactively for tasks with 3+ distinct steps. "
        "Call with merge=false to initialize a new list. Call with merge=true to "
        "update status of existing items. Each item has id, content, and status "
        "(pending/in_progress/completed/cancelled)."
    )
    category: EToolCategory = EToolCategory.AGENT
    parameters: dict = {
        "type": "object",
        "properties": {
            "merge": {
                "type": "boolean",
                "description": (
                    "Whether to merge the todos with the existing list. "
                    "true = update existing items, false = replace all."
                ),
            },
            "todos": {
                "type": "array",
                "description": "JSON string of todo items array.",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": "Unique identifier for the todo item.",
                        },
                        "content": {
                            "type": "string",
                            "description": "Description of the task.",
                        },
                        "status": {
                            "type": "string",
                            "enum": ["pending", "in_progress", "completed", "cancelled"],
                            "description": "Current status of the task.",
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

        validStatuses = {"pending", "in_progress", "completed", "cancelled"}
        for i, item in enumerate(todos):
            if not isinstance(item, dict):
                return ToolResult.Fail(
                    f"todos[{i}] must be an object", toolName=self.name,
                )
            if "id" not in item or "content" not in item or "status" not in item:
                return ToolResult.Fail(
                    f"todos[{i}] missing required field (id/content/status)",
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
            "pending": "   ",
            "in_progress": "-> ",
            "completed": "[x]",
            "cancelled": "[-]",
        }
        for item in todos:
            icon = statusIcons.get(item["status"], " ? ")
            lines.append(f"  {icon} [{item['id']}] {item['content']}")

        return ToolResult.Ok("\n".join(lines), toolName=self.name)
