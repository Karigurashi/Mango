"""IChannelComponent 抽象基类 —— 所有可挂载到 BaseChannel 的组件必须实现的接口。

【重要约束】
- 所有 Component 子类 MUST NOT 在构造函数（__init__）中接收任何业务参数。
  构造函数仅用于字段默认值初始化，保证无参构造。
- OnInitialize(channel) 才是真正的初始化入口：
  在此通过 channel._xxxComponent 访问其他组件、完成依赖注入与业务初始化。
- OnDestroy() 在组件被销毁时回调，用于资源清理。

BaseChannel.__init__ 中无参构造实例并立即调用 OnInitialize(channel)，
StopAsync 时调用 OnDestroy()。
"""

from __future__ import annotations

from abc import ABC
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .baseChannel import BaseChannel


class IChannelComponent(ABC):
    """Channel 组件接口 —— 定义初始化 / 销毁生命周期。

    构造函数: MUST NOT 接收业务参数，仅做字段默认值初始化。
    OnInitialize(channel): 由 BaseChannel.__init__ 显式调用，
                            通过 channel._xxxComponent 注入依赖。
    OnDestroy: StopAsync 时回调，用于资源清理。
    """

    def OnInitialize(self, channel: BaseChannel) -> None:
        """初始化回调，由 BaseChannel.__init__ 显式调用。

        子类 override 此方法，通过 channel._xxxComponent 注入依赖。

        Args:
            channel: 当前所属的 BaseChannel 实例。
        """
        pass

    def OnDestroy(self) -> None:
        """销毁回调，由 BaseChannel.StopAsync 调用。

        子类 override 此方法执行清理逻辑。
        """
        pass
