"""内置工具包 —— 按分类组织，框架自带的 Agent 工具。

目录结构::

    builtin/
    ├── file/       # 文件操作 (读/写/删/搜/grep)
    ├── shell/      # Shell 命令执行
    └── network/    # 网络操作 (网页抓取/搜索)
"""

from .file import (
    ReadFileTool,
    WriteFileTool,
    DeleteFileTool,
    ListDirTool,
    SearchFileTool,
    GrepCodeTool,
)
from .shell import BashTool
from .network import (
    FetchContentTool,
    SearchWebTool,
)

__all__ = [
    "ReadFileTool",
    "WriteFileTool",
    "DeleteFileTool",
    "ListDirTool",
    "SearchFileTool",
    "GrepCodeTool",
    "BashTool",
    "FetchContentTool",
    "SearchWebTool",
]
