"""序列化/反序列化工具类。

四种转换，覆盖对象 ↔ JSON ↔ dict 全路径：
- ToJson:   对象 → JSON 字符串
- ToDict:   对象 → dict
- FromJson: JSON 字符串 → 对象
- FromDict: dict → 对象
"""

from __future__ import annotations

import json
from dataclasses import asdict, fields, is_dataclass
from typing import Any, Optional, Type, TypeVar

T = TypeVar("T")


class SerializeUtil:
    """序列化静态工具类，提供对象 ↔ JSON ↔ dict 四种转换。"""

    # ==================== 公开 API ====================

    @staticmethod
    def ToJson(obj: Any, indent: Optional[int] = None) -> str:
        """对象 → JSON 字符串。

        Args:
            obj: 任意 Python 对象（dataclass / Pydantic / 普通对象等）。
            indent: 可选，缩进空格数，None 表示紧凑输出。

        Example:
            jsonStr = SerializeUtil.ToJson(config, indent=2)
        """
        return json.dumps(obj, ensure_ascii=False, indent=indent, default=SerializeUtil._Default)

    @staticmethod
    def ToDict(obj: Any) -> Any:
        """对象 → dict / list。

        内部走 JSON 往返，覆盖所有 _Default 支持的类型（datetime、enum 等）。

        Example:
            d = SerializeUtil.ToDict(config)
        """
        return json.loads(SerializeUtil.ToJson(obj))

    @staticmethod
    def FromJson(jsonStr: str, targetType: Optional[Type[T]] = None) -> Any:
        """JSON 字符串 → 对象。

        Args:
            jsonStr: JSON 字符串。
            targetType: 可选，目标类型（Pydantic BaseModel / dataclass / 普通类）。
                       传入时返回强类型实例，不传则返回 dict/list。

        Example:
            config = SerializeUtil.FromJson(jsonStr, ModelConfig)
        """
        if targetType is None:
            return json.loads(jsonStr)
        return SerializeUtil._DeserializeTyped(jsonStr, targetType)

    @staticmethod
    def FromDict(data: dict[str, Any], targetType: Type[T]) -> T:
        """dict → 对象。

        自动识别类型：Pydantic BaseModel > dataclass > 普通类。

        Example:
            config = SerializeUtil.FromDict(agentData, AgentConfig)
        """
        if hasattr(targetType, "model_validate"):
            return targetType.model_validate(data)
        if hasattr(targetType, "__dataclass_fields__"):
            return SerializeUtil._DataclassFromDict(targetType, data)
        return targetType(**data)

    # ==================== 内部实现 ====================

    @staticmethod
    def _DeserializeTyped(jsonStr: str, targetType: Type[T]) -> T:
        """JSON 字符串 → 指定类型实例（内部，由 FromJson 调用）。"""
        if hasattr(targetType, "model_validate"):
            return targetType.model_validate_json(jsonStr)

        data = json.loads(jsonStr)

        if hasattr(targetType, "__dataclass_fields__"):
            return SerializeUtil._DataclassFromDict(targetType, data)

        if isinstance(data, dict):
            return targetType(**data)
        return targetType(data)

    @staticmethod
    def _DataclassFromDict(
        cls: type,
        data: dict[str, Any],
        fieldGroups: Optional[dict[str, Optional[str]]] = None,
        overrideDefaults: Optional[dict[str, Any]] = None,
    ) -> Any:
        """dict → dataclass 实例（内部使用）。

        每个字段按优先级取值：
        1. data[group][fieldName] — fieldGroups 指定的嵌套分组
        2. data[fieldName] — 顶层扁平键
        3. field.default — dataclass 声明的默认值
        4. overrideDefaults[fieldName] — 调用方覆盖默认值
        """
        if fieldGroups is None:
            fieldGroups = {}
        if overrideDefaults is None:
            overrideDefaults = {}

        kwargs: dict[str, Any] = {}
        for f in fields(cls):
            group = fieldGroups.get(f.name)
            default = overrideDefaults.get(f.name, f.default)

            if group is not None:
                groupData = data.get(group, {})
                if not isinstance(groupData, dict):
                    groupData = data
                kwargs[f.name] = groupData.get(f.name, data.get(f.name, default))
            else:
                kwargs[f.name] = data.get(f.name, default)

        return cls(**kwargs)

    @staticmethod
    def _Default(obj: Any) -> Any:
        """JSON 序列化失败时的回落回调。"""
        if is_dataclass(obj) and not isinstance(obj, type):
            return asdict(obj)
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        if hasattr(obj, "__dict__"):
            return obj.__dict__
        return str(obj)
