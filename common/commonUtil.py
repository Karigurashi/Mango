import json
from pathlib import Path
from typing import Any, Optional, Type, TypeVar

T = TypeVar("T")


class CommonUtil:
    """通用静态工具类，提供 JSON 序列化/反序列化等基础能力"""

    @staticmethod
    def JsonSerialize(obj: Any, indent: Optional[int] = None) -> str:
        """将 Python 对象序列化为 JSON 字符串"""
        return json.dumps(obj, ensure_ascii=False, indent=indent, default=CommonUtil._JsonDefault)

    @staticmethod
    def JsonDeserialize(jsonStr: str, targetType: Optional[Type[T]] = None) -> Any:
        """将 JSON 字符串反序列化为 Python 对象。

        Args:
            jsonStr: JSON 字符串。
            targetType: 可选，目标类型（Pydantic BaseModel / dataclass / 普通类）。
                       传入时直接返回强类型实例，不传则返回 dict/list。

        Returns:
            反序列化后的 Python 对象。指定 targetType 时返回对应类型实例。

        Example:
            config = CommonUtil.JsonDeserialize(jsonStr, ModelConfig)
        """
        if targetType is None:
            return json.loads(jsonStr)
        return CommonUtil._DeserializeTyped(jsonStr, targetType)

    @staticmethod
    def JsonSaveToFile(obj: Any, filePath: str, indent: int = 2) -> None:
        """将 Python 对象保存为 JSON 文件"""
        content = CommonUtil.JsonSerialize(obj, indent=indent)
        Path(filePath).write_text(content, encoding="utf-8")

    @staticmethod
    def JsonLoadFromFile(filePath: str, targetType: Optional[Type[T]] = None) -> Any:
        """从 JSON 文件中读取并反序列化。

        Args:
            filePath: JSON 文件路径。
            targetType: 可选，目标类型。传入时直接返回强类型实例。

        Example:
            config = CommonUtil.JsonLoadFromFile("models.json", ModelConfig)
        """
        content = Path(filePath).read_text(encoding="utf-8")
        return CommonUtil.JsonDeserialize(content, targetType=targetType)

    # ==================== 内部实现 ====================

    @staticmethod
    def _DeserializeTyped(jsonStr: str, targetType: Type[T]) -> T:
        """将 JSON 字符串反序列化为指定类型实例。

        自动识别类型并选择最优路径：Pydantic BaseModel > dataclass > 普通类。
        嵌套对象由各自的 __init__ 负责递归转换，不再使用全局 object_hook。
        """
        # Pydantic BaseModel（优先级最高，带类型校验，天然支持嵌套模型）
        if hasattr(targetType, "model_validate"):
            return targetType.model_validate_json(jsonStr)

        # 普通类 / dataclass：先解析为原生 dict，再调用构造函数
        data = json.loads(jsonStr)
        if isinstance(data, dict):
            return targetType(**data)
        # JSON 根节点为数组时，作为单个位置参数传入
        return targetType(data)

    @staticmethod
    def _JsonDefault(obj: Any) -> Any:
        """JSON 序列化失败时回调，处理 datetime 等非原生可序列化类型"""
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        if hasattr(obj, "__dict__"):
            return obj.__dict__
        return str(obj)