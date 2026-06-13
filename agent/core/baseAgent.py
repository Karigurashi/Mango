"""BaseAgent —— Agent 体系基类，组合 Component 封装各项能力。

内置 Component 容器，通过组合模式持有各 IComponent 子类实例，
子类可 override 任意方法注入 harness 逻辑（上下文组装、ReAct 循环等）。

【Component 生命周期】
1. AddComponent<T>()  —— 无参构造实例。
2. InitAllComponents() —— 统一调用 OnInitialize(agent)，完成依赖注入。
3. RemoveComponent / Destroy —— 调用 OnDestroy()，执行清理。
"""

from __future__ import annotations

from typing import AsyncIterator, Dict, List, Optional, Type, TypeVar

from .baseComponent import IComponent

T = TypeVar("T", bound=IComponent)


class BaseAgent:
    """Agent 体系基类 —— 通过组合模式持有各 Component 实例。"""

    def __init__(self) -> None:
        self._components: Dict[Type[IComponent], IComponent] = {}

    # ---- Component 管理 ----

    def AddComponent(self, compType: Type[T]) -> T:
        """挂载指定类型 Component，无参构造实例。

        若同类型已存在，直接返回已有实例，不重复构造。
        构造函数 MUST NOT 接收业务参数，真正的初始化在 OnInitialize 中完成。

        Args:
            compType: Component 类型（泛型 T）。

        Returns:
            挂载的 Component 实例。
        """
        existing = self._components.get(compType)
        if existing is not None:
            return existing  # type: ignore[return-value]

        component = compType()
        self._components[compType] = component
        return component

    def InitAllComponents(self) -> None:
        """统一初始化所有已挂载 Component。

        按挂载顺序依次调用各 Component 的 OnInitialize(self)，
        传入当前 Agent 实例，完成依赖注入。
        应在全部 AddComponent 完成后调用。
        """
        for component in self._components.values():
            component.OnInitialize(self)

    def RemoveComponent(self, compType: Type[T]) -> Optional[T]:
        """卸载指定类型 Component，返回被移除的实例。

        若该类型未挂载则返回 None。
        """
        component = self._components.pop(compType, None)
        if component is not None:
            component.OnDestroy()
        return component  # type: ignore[return-value]

    def GetComponent(self, compType: Type[T]) -> Optional[T]:
        """获取指定类型 Component，未挂载返回 None。"""
        return self._components.get(compType, None)  # type: ignore[return-value]

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

    # ---- 运行时生命周期模板方法 ----

    async def RunWithLifecycleAsync(
        self,
        coreAsyncIterator: AsyncIterator,
    ) -> AsyncIterator:
        """生命周期保证模板方法：包装子类的核心异步迭代器，确保 AfterTurnAsync 在所有路径执行。

        无论核心循环正常结束、抛异常、被取消还是超限，
        finally 中的 AfterTurnAsync 都会被调用，避免内存泄漏
        （已压缩消息未 Purge、外存文件未 Cleanup、会话摘要未持久化）。

        子类只需实现核心逻辑并传入 async generator，
        生命周期保证由基类自动提供，无需每个子类各自写 try/finally。

        Args:
            coreAsyncIterator: 子类的核心异步迭代器（如 _RunReActCoreAsync 的返回值）。

        Yields:
            核心迭代器产生的每个事件。
        """
        from agent.component.contex.contextComponent import ContextComponent

        normalExit = False
        try:
            async for event in coreAsyncIterator:
                yield event
            normalExit = True
        finally:
            ctxComp = self.GetComponent(ContextComponent)
            if ctxComp is not None:
                await ctxComp.AfterTurnAsync()
            if not normalExit:
                from agent.component.data.dataComponent import DataComponent
                from agent.component.data.eAgentState import EAgentState
                dataComp = self.GetComponent(DataComponent)
                if dataComp is not None:
                    dataComp.state = EAgentState.ERROR
