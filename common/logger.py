"""统一日志管理器，静态类，极简调用。

使用方式::
    Logger.Info("模型调用成功")
    Logger.Error("请求超时")
    Logger.Warning("重试中")
    Logger.Debug("raw response: ...")
"""

from __future__ import annotations

import logging
import sys


class Logger:
    """全局日志静态类，封装 logging.Logger。"""

    _instance: logging.Logger | None = None

    @classmethod
    def _EnsureLoaded(cls) -> None:
        if cls._instance is not None:
            return
        cls._instance = logging.getLogger("Brain")
        cls._instance.setLevel(logging.DEBUG)
        if not cls._instance.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setLevel(logging.DEBUG)
            fmt = logging.Formatter(
                "[%(asctime)s] [%(levelname)-5s] [%(name)s] %(message)s",
                datefmt="%H:%M:%S",
            )
            handler.setFormatter(fmt)
            cls._instance.addHandler(handler)

    # ---- 公开方法 ----

    @classmethod
    def Info(cls, msg: str, *args: object) -> None:
        cls._EnsureLoaded()
        cls._instance.info(msg, *args)

    @classmethod
    def Warning(cls, msg: str, *args: object) -> None:
        cls._EnsureLoaded()
        cls._instance.warning(msg, *args)

    @classmethod
    def Error(cls, msg: str, *args: object) -> None:
        cls._EnsureLoaded()
        cls._instance.error(msg, *args)

    @classmethod
    def Debug(cls, msg: str, *args: object) -> None:
        cls._EnsureLoaded()
        cls._instance.debug(msg, *args)

    # ---- 日志级别控制 ----

    @classmethod
    def SetLevel(cls, level: int) -> None:
        cls._EnsureLoaded()
        cls._instance.setLevel(level)

    @classmethod
    def GetLogger(cls) -> logging.Logger:
        """返回底层 logging.Logger，供需要定制格式的场景使用。"""
        cls._EnsureLoaded()
        return cls._instance
