"""Agent CLI 终端入口点 —— 支持 ``python -m agent.cli`` 启动。

Usage::

    python -m agent.cli
    python -m agent.cli deepseek-mid   # 指定模型
"""

from __future__ import annotations

import sys

from .cliApp import CliApp


def main() -> None:
    """CLI 入口函数，解析命令行参数并启动 REPL。"""
    modelName: str | None = None
    if len(sys.argv) > 1:
        modelName = sys.argv[1]

    app = CliApp(modelName=modelName)
    app.Run()


if __name__ == "__main__":
    main()
