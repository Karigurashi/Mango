"""BaseAgent —— Agent 体系基类，组合 Component 封装各项能力。

内置 Component 容器，通过组合模式持有各 IComponent 子类实例，
子类可 override 任意方法注入 harness 逻辑（上下文组装、ReAct 循环等）。

【Component 生命周期 —— 能力即用即取】
1. AddComponent<T>()  —— 无参构造实例，注册时自动触发 OnInitialize 完成依赖注入。
2. GetComponent<T>()  —— 若未创建则自动构造并初始化。
3. RemoveComponent / Destroy —— 调用 OnDestroy()，执行清理。
"""

from __future__ import annotations

import abc
from typing import Dict, List, Optional, Type, TypeVar

from common.cancellationToken import CancellationToken
from .baseComponent import IComponent

T = TypeVar("T", bound=IComponent)


class BaseAgent(abc.ABC):
    """Agent 体系基类 —— 通过组合模式持有各 Component 实例。"""

    def __init__(self) -> None:
        self._components: Dict[Type[IComponent], IComponent] = {}

    @abc.abstractmethod
    async def RunStreamAsync(
        self,
        userMessage: str,
        cancellationToken: Optional[CancellationToken] = None,
    ) -> None:
        """异步流式执行 Agent 主循环，事件通过 EventBusComponent 推送。
        
        Args:
            userMessage: 用户/外部注入的消息文本。
            cancellationToken: 可选取消令牌。
        """
        ...

    # ---- Component 管理 ----

    def AddComponent(self, compType: Type[T]) -> T:
        """注册指定类型 Component，无参构造实例并自动触发 OnInitialize。

        若同类型已存在，直接返回已有实例，不重复构造。

        Args:
            compType: Component 类型（泛型 T）。

        Returns:
            已初始化的 Component 实例。
        """
        return self.GetComponent(compType, isGenerate=True)  # type: ignore[return-value]

    def GetComponent(self, compType: Type[T], isGenerate: bool = True) -> Optional[T]:
        """获取指定类型 Component。

        isGenerate=True（默认）：未创建时自动构造并触发 OnInitialize。
        isGenerate=False：仅查找已挂载实例，未找到返回 None。

        Args:
            compType: Component 类型（泛型 T）。
            isGenerate: 未找到时是否自动创建。

        Returns:
            已初始化的 Component 实例，isGenerate=False 且未挂载时返回 None。
        """
        component = self._components.get(compType)
        if component is not None:
            return component  # type: ignore[return-value]
        if not isGenerate:
            return None

        component = compType()
        self._components[compType] = component
        component.OnInitialize(self)
        return component  # type: ignore[return-value]

    def RemoveComponent(self, compType: Type[T]) -> Optional[T]:
        """卸载指定类型 Component，返回被移除的实例。

        若该类型未挂载则返回 None。
        """
        component = self._components.pop(compType, None)
        if component is not None:
            component.OnDestroy()
        return component  # type: ignore[return-value]

    def HasComponent(self, compType: Type[IComponent]) -> bool:
        """检查是否已挂载指定类型 Component。"""
        return compType in self._components

    def GetAllComponents(self) -> List[IComponent]:
        """返回所有已挂载 Component 的列表。"""
        return list(self._components.values())

    def Destroy(self) -> None:
        """卸载全部 Component 并清空容器。"""
        for component in list(self._components.values()):
            component.OnDestroy()
        self._components.clear()
