"""BaseAgent —— Agent 体系基类，组合 Component 封装各项能力。

内置 Component 容器，通过组合模式持有各 IComponent 子类实例，
子类可 override 任意方法注入 harness 逻辑（上下文组装、ReAct 循环等）。

【Component 生命周期 —— 能力即用即取】
1. AddComponent<T>()  —— 无参构造实例并注册（不触发 OnInitialize）。
2. GetComponent<T>()  —— 若未创建则自动构造，首次访问时触发 OnInitialize 完成依赖注入。
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
        self._initializedComponents: set[Type[IComponent]] = set()

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
        """注册指定类型 Component，无参构造实例（不触发 OnInitialize）。

        若同类型已存在，直接返回已有实例，不重复构造。
        适用于需要在 OnInitialize 前注入外部依赖的场景（如 DataComponent.llm）。
        OnInitialize 在首次 GetComponent 时自动触发。

        Args:
            compType: Component 类型（泛型 T）。

        Returns:
            注册的 Component 实例。
        """
        existing = self._components.get(compType)
        if existing is not None:
            return existing  # type: ignore[return-value]

        component = compType()
        self._components[compType] = component
        return component

    def GetComponent(self, compType: Type[T]) -> T:
        """获取指定类型 Component，未创建时自动构造并触发 OnInitialize。

        若 Component 尚未创建，先无参构造实例，再调用 OnInitialize(self)
        完成依赖注入。已通过 AddComponent 预注册但尚未初始化的 Component
        也会在此次首次访问时完成初始化。

        Args:
            compType: Component 类型（泛型 T）。

        Returns:
            已初始化的 Component 实例，保证非 None。
        """
        component = self._components.get(compType)
        if component is None:
            component = compType()
            self._components[compType] = component

        if compType not in self._initializedComponents:
            self._initializedComponents.add(compType)
            component.OnInitialize(self)

        return component  # type: ignore[return-value]

    def RemoveComponent(self, compType: Type[T]) -> Optional[T]:
        """卸载指定类型 Component，返回被移除的实例。

        若该类型未挂载则返回 None。
        """
        component = self._components.pop(compType, None)
        if component is not None:
            self._initializedComponents.discard(compType)
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
        self._initializedComponents.clear()
