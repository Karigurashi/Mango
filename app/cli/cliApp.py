"""CliApp —— CLI REPL 主编排器，继承 BaseChannel。

作为 BaseChannel 的 CLI 平台适配器：
- 单群模式（groupId="cli"），一个 Agent 实例服务终端用户。
- 消息前缀匹配（/）走指令分发，否则走 Agent 执行。
- Agent 事件通过 OnAgentEventSync 转发给 CliRenderer 实时渲染。
- 保留 CLI 特有交互层：REPL 循环、Ctrl+C 信号。

对标 Claude Code CLI 交互模式：斜杠指令 + 普通消息 + Ctrl+C 取消。
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
import traceback
from typing import Optional

from agent import Agent, AgentManager, AgentStreamEvent, LLMComponent, SessionComponent
from agent.component.data import AgentConfig
from common.cancellationToken import CancellationToken
from common.logger import Logger

from ..channel import BaseChannel, ChannelConfig, ChannelMessage, EChannelState
from .cliCommand import CliContext
from .cliConfig import CliConfig
from .cliRenderer import CliRenderer


class CliApp(BaseChannel):
    """CLI REPL 主编排器 —— BaseChannel 的终端适配器。

    创建单群（groupId="cli"）Channel，Agent 事件转发给 CliRenderer，
    斜杠指令通过 BaseChannel 指令系统分发。

    Usage::

        app = CliApp("deepseek-high")
        app.Run()  # 同步入口，内部调用 asyncio.run()
    """

    CLI_GROUP_ID: str = "cli"

    def __init__(
        self,
        modelName: Optional[str] = None,
        config: Optional[CliConfig] = None,
    ) -> None:
        super().__init__(ChannelConfig(
            modelName=modelName,
            enableWorkflow=True,
            commandPrefix="/",
        ))

        self._cliConfig: CliConfig = config or CliConfig()
        self._renderer: CliRenderer = CliRenderer(self._cliConfig)
        self._activeToken: Optional[CancellationToken] = None

        # 创建 CLI 单群（触发 CreateAgent + OnGroupCreated）
        self._cliGroup = self.EnsureGroup(self.CLI_GROUP_ID, "CLI")

        Logger.RedirectToStdout()
        Logger.SetLevel(logging.WARNING)
        self._EnsureUtf8Stdout()
        self._PrintBanner()
        signal.signal(signal.SIGINT, self._OnInterrupt)

    # ---- BaseChannel 钩子 ----

    def CreateAgent(self, groupId: str) -> Agent:
        """override: 创建带 workflow 的 Agent，tasksDir 按 groupId 隔仓。"""
        agentConfig = AgentConfig()
        agentConfig.enableWorkflow = self._config.enableWorkflow
        agentConfig.enableSchedule = self._config.enableSchedule
        agentConfig.tasksDir = os.path.join(agentConfig.tasksDir, groupId)
        return AgentManager.CreateAgent(self._config.modelName, agentConfig)

    def OnAgentEventSync(self, groupId: str, event: AgentStreamEvent) -> None:
        """override: Agent 事件 → CliRenderer 实时渲染。"""
        self._renderer.OnEvent(event)

    def CreateCommandContext(self, groupContext, message: ChannelMessage) -> CliContext:
        """override: 返回 CliContext（终端即时输出）。"""
        return CliContext(
            channel=self,
            groupContext=groupContext,
            message=message,
            registry=self._commandRegistry,
            cliConfig=self._cliConfig,
            renderer=self._renderer,
        )

    async def OnSendResponseAsync(
        self,
        groupId: str,
        content: str,
        cancellationToken: Optional[CancellationToken] = None,
    ) -> None:
        """override: CLI 指令通过 CliContext.Print* 直接输出，不需要异步投递。"""
        pass

    # ---- 便捷访问 ----

    @property
    def _agent(self) -> Agent:
        """CLI 群组的 Agent 实例。"""
        return self._cliGroup.agent


    async def OnStartAsync(
        self,
        cancellationToken: Optional[CancellationToken] = None,
    ) -> None:
        """override: CLI 主循环，阻塞直到退出。

        REPL 循环驱动：读取用户输入 → 指令分发或 Agent 执行。
        /exit 指令或 Ctrl+C（空闲时）设置 STOPPING 退出循环。
        """
        try:
            while self._state == EChannelState.RUNNING:
                self._PrintPrompt()
                userInput = await asyncio.get_running_loop().run_in_executor(
                    None, sys.stdin.readline,
                )
                if not userInput:  # EOF
                    self._state = EChannelState.STOPPING
                    break
                userInput = userInput.rstrip('\n\r')
                if not userInput:
                    continue
                await self._ProcessInputAsync(userInput)
        finally:
            await self.StopAsync()
            self._PrintGoodbye()

    # ---- 输入处理 ----

    async def _ProcessInputAsync(self, userInput: str) -> None:
        """处理一条用户输入（指令或消息）。

        Args:
            userInput: 用户原始输入。
        """
        isCommand = userInput.startswith(self._config.commandPrefix)
        msg = ChannelMessage(
            groupId=self.CLI_GROUP_ID,
            userId="user",
            content=userInput,
        )

        if not isCommand:
            self._activeToken = CancellationToken()

        try:
            await self.ReceiveMessageAsync(msg, self._activeToken)
        except Exception:
            traceback.print_exc()
        finally:
            if not isCommand:
                self._activeToken = None
                self._PrintUsageFooter()

    # ---- 信号处理 ----

    def _OnInterrupt(self, signum: int, frame: object) -> None:
        """统一 SIGINT 处理器，根据 Agent 忙闲状态分流。

        - Agent 忙: 取消当前执行。
        - Agent 闲: 直接退出 REPL。
        """
        if self._activeToken is not None:
            self._activeToken.Cancel()
            c = self._cliConfig
            sys.stdout.write(f"\n{c.Color('[Cancelling...]', c.AMBER)}\n")
            sys.stdout.flush()
        else:
            self._state = EChannelState.STOPPING

    # ---- Banner / Prompt / Goodbye ----

    def _PrintBanner(self) -> None:
        """打印 CLI 欢迎横幅。"""
        modelName = self._agent.GetComponent(LLMComponent).modelName
        sessionId = self._agent.GetComponent(SessionComponent).ActiveSessionId
        self._renderer.PrintBanner(modelName, sessionId)

    def _PrintGoodbye(self) -> None:
        """打印退出信息。"""
        c = self._cliConfig
        sys.stdout.write(c.Dim(f"\n  {c.BOX_BL}{c.BOX_H * 20} See you {c.BOX_BR}\n\n"))
        sys.stdout.flush()

    def _PrintPrompt(self) -> None:
        """打印 REPL 提示符。

        IDLE 时显示紫色箭头，RUNNING 时不显示提示符。
        """
        if self._activeToken is not None:
            return
        c = self._cliConfig
        sys.stdout.write(f"{c.Color(c.ICON_PROMPT, c.PURPLE)} ")
        sys.stdout.flush()

    def _PrintUsageFooter(self) -> None:
        """打印本轮 Token 用量页脚。"""
        if not self._cliConfig.showTokenUsage:
            return
        llmComp = self._agent.GetComponent(LLMComponent)
        modelName = llmComp.modelName
        promptTokens = llmComp.LastPromptTokens
        completionTokens = llmComp.LastCompletionTokens
        cacheHitRate = llmComp.LastCacheHitRate
        if promptTokens == 0 and completionTokens == 0:
            return
        self._renderer.PrintFooter(modelName, promptTokens, completionTokens, cacheHitRate)

    # ---- 工具方法 ----

    @staticmethod
    def _EnsureUtf8Stdout() -> None:
        """确保 stdout 使用 UTF-8 编码（Windows 兼容）。"""
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except (AttributeError, OSError):
            pass
