"""环境快照 —— 采集 Agent 运行时的基础环境信息，注入 LOD0 Context。"""

from __future__ import annotations

import os
import platform
import sys


def GetEnvironmentSnapshot(workspaceRoot: str | None = None) -> str:
    """生成环境快照文本块。

    Args:
        workspaceRoot: 工作区根目录，默认当前工作目录。

    Returns:
        包裹在 ``<environment>`` 标签内的快照文本。
    """
    cwd = workspaceRoot or os.getcwd()
    lines = [
        "<environment>",
        f"OS: {platform.system()} {platform.release()}",
        f"Python: {sys.version.split()[0]}",
        f"Workspace: {cwd}",
        "</environment>",
    ]
    return "\n".join(lines)
