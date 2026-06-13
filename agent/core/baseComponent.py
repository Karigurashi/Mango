"""IComponent 抽象基类 —— 所有可挂载模块必须实现的接口。

【重要约束】
- 所有 Component 子类 MUST NOT 在构造函数（__init__）中接收任何业务参数。
  构造函数仅用于字段默认值初始化，保证 AddComponent 可无参构造。
- OnInitialize(agent) 才是真正的初始化入口：
  在此通过 agent.GetComponent() 获取其他组件、完成依赖注入与业务初始化。
- OnDestroy() 在组件被卸载时回调，用于资源清理。

BaseAgent.AddComponent<T>() 内部无参构造实例，
InitAllComponents() 统一调用 OnInitialize(agent)，
RemoveComponent / Destroy 时调用 OnDestroy()。
"""

from __future__ import annotations

from abc import ABC
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .baseAgent import BaseAgent


class IComponent(ABC):
    """组件接口 —— 定义挂载 / 卸载生命周期。

    构造函数: MUST NOT 接收业务参数，仅做字段默认值初始化。
    OnInitialize(agent): 挂载后由 InitAllComponents 统一调用，
                         通过 agent.GetComponent() 注入依赖。
    OnDestroy: 卸载时回调，用于资源清理。
    """

    def OnInitialize(self, agent: BaseAgent) -> None:
        """挂载后初始化回调。

        由 BaseAgent.InitAllComponents() 统一调用，传入所属 Agent 实例。
        子类 override 此方法，通过 agent.GetComponent() 注入依赖。

        Args:
            agent: 当前所属的 BaseAgent 实例。
        """
        pass

    def OnDestroy(self) -> None:
        """从 BaseAgent 卸载时回调。

        子类 override 此方法执行清理逻辑。
        """
        pass
