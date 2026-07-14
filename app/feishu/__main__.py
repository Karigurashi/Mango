"""飞书机器人通道入口点 —— 支持 ``python -m app.feishu`` 启动。

Usage::

    python -m app.feishu
    python -m app.feishu <app_id> <app_secret>
    python -m app.feishu <app_id> <app_secret> deepseek-high
"""

from __future__ import annotations

import sys

from .feishuChannel import FeishuChannel
from .feishuConfig import FeishuConfig


def main() -> None:
    """飞书通道入口函数，解析命令行参数并启动 WebSocket 长连接。"""
    appId: str = ""
    appSecret: str = ""
    modelName: str | None = None

    if len(sys.argv) > 1:
        appId = sys.argv[1]
    if len(sys.argv) > 2:
        appSecret = sys.argv[2]
    if len(sys.argv) > 3:
        modelName = sys.argv[3]

    config = FeishuConfig(
        appId=appId,
        appSecret=appSecret,
        modelName=modelName,
    )
    channel = FeishuChannel(config)
    channel.Start()


if __name__ == "__main__":
    main()
