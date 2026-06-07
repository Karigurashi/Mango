"""LOD 四级分级枚举 —— 控制上下文内容的压缩与丢弃策略。"""

from enum import Enum


class EContextLodLevel(Enum):
    """上下文内容分级 —— 决定压缩策略、丢弃权限、注入行为。

    Attributes:
        RESIDENT (0): 常驻不压缩，不可丢弃（System Prompt、核心指令）。
        SUMMARIZABLE (1): 可压缩为摘要，不可丢弃（用户偏好、重要决策）。
        DISCARDABLE (2): 可压缩，token 不足时可丢弃（旧工具结果、思考过程）。
        EXTERNAL_ONLY (3): 不注入上下文，仅路径引用（大文件、工具原始输出）。
    """

    RESIDENT = 0
    SUMMARIZABLE = 1
    DISCARDABLE = 2
    EXTERNAL_ONLY = 3

    def CanCompress(self) -> bool:
        """是否可压缩为摘要。LOD 1/2 可压缩。"""
        return self in (EContextLodLevel.SUMMARIZABLE, EContextLodLevel.DISCARDABLE)

    def CanDiscard(self) -> bool:
        """是否可在 token 不足时丢弃。仅 LOD 2 可丢弃。"""
        return self == EContextLodLevel.DISCARDABLE

    def ShouldInject(self) -> bool:
        """是否注入上下文。LOD 0/1/2 注入，LOD 3 不注入。"""
        return self != EContextLodLevel.EXTERNAL_ONLY

    def __repr__(self) -> str:
        return f"EContextLodLevel.{self.name}"
