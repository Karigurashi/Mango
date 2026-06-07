"""LLM 模型档位枚举，用于按能力级别调度模型。"""

from __future__ import annotations

from enum import Enum


class ETier(Enum):
    """模型能力档位。

    HIGH: 最强模型，用于复杂推理、代码生成等重度任务。
    MID:  中等模型，日常对话与轻量任务。
    LOW:  轻量模型，用于简单分类、摘要等低成本任务。
    """

    HIGH = "high"
    MID = "mid"
    LOW = "low"
