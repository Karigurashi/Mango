"""记忆分类枚举 —— 对应 Karpathy LLM Wiki 四类记忆体系。

偏好(Preference)、决策(Decision)、模式(Pattern)、引用(Reference)。

业务必要性注释：
    枚举值即磁盘目录名（preferences/decisions/patterns/references），
    FromDirName / DirName 均依赖字符串值做路径映射，故使用 str 枚举。
"""

from enum import Enum


class EMemoryCategory(str, Enum):
    """记忆语义分类，值即对应 memory/ 下的子目录名。

    Attributes:
        PREFERENCE: 用户偏好（编码风格、工具选择、命名习惯）。
        DECISION:  架构决策（技术选型、设计取舍、迁移方案）。
        PATTERN:   反馈模式（纠错规则、确认的正确做法）。
        REFERENCE: 外部引用（API 文档链接、看板地址、联系人）。
    """

    PREFERENCE = "preferences"
    DECISION = "decisions"
    PATTERN = "patterns"
    REFERENCE = "references"

    @property
    def DirName(self) -> str:
        """对应 memory/ 下的子目录名（即枚举值自身）。"""
        return self.value

    @property
    def Label(self) -> str:
        """中文标签。"""
        return {
            EMemoryCategory.PREFERENCE: "偏好",
            EMemoryCategory.DECISION: "决策",
            EMemoryCategory.PATTERN: "模式",
            EMemoryCategory.REFERENCE: "引用",
        }[self]

    @staticmethod
    def FromDirName(dirName: str) -> "EMemoryCategory | None":
        """从目录名或分类名（兼容单复数）还原枚举。

        支持 'preferences' / 'preference' 两种输入。
        """
        # 先尝试直接构造（复数目录名）
        try:
            return EMemoryCategory(dirName)
        except ValueError:
            pass
        # 兼容 LLM 输出的单数形式
        singularMap = {
            "preference": EMemoryCategory.PREFERENCE,
            "decision": EMemoryCategory.DECISION,
            "pattern": EMemoryCategory.PATTERN,
            "reference": EMemoryCategory.REFERENCE,
        }
        return singularMap.get(dirName)
