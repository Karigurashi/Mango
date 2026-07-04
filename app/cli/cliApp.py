"""CliApp —— CLI REPL 主编排器。

创建 Agent、订阅渲染器、驱动 REPL 循环、管理信号与取消。
对标 Claude Code CLI 交互模式：斜杠指令 + 普通消息 + Ctrl+C 取消 +
运行时消息队列（Agent 执行期间用户可继续输入，消息自动入队依次处理）。
"""

from __future__ import annotations

import asyncio
import logging
from operator import truediv
import signal
import sys
import threading
import traceback
from typing import Optional

from agent import (
    AgentManager,
    EventBusComponent,
    LLMComponent,
    SessionComponent,
)

from agent.component.data import AgentConfig
from common.cancellationToken import CancellationToken
from common.logger import Logger

from .builtinCommands import RegisterBuiltinCommands
from .cliCommand import CliContext
from .cliCommandRegistry import CliCommandRegistry
from .cliConfig import CliConfig
from .cliRenderer import CliRenderer
from .eCliState import ECliState


class CliApp:
    """CLI REPL 主编排器。

    创建 Agent 实例、订阅渲染器到 EventBusComponent、
    驱动 REPL 循环（输入 → 分发斜杠指令或执行 Agent），
    管理 Ctrl+C 信号与 CancellationToken 生命周期。

    Agent 执行期间用户可继续输入消息，消息自动入队，
    当前轮结束后依次处理队列中的消息。

    Usage::

        app = CliApp("deepseek-high")
        app.Run()  # 同步入口，内部调用 asyncio.run()
    """

    def __init__(
        self,
        modelName: Optional[str] = None,
        config: Optional[CliConfig] = None,
    ) -> None:
        self._config = config or CliConfig()

        agentConfig = AgentConfig()
        agentConfig.enableWorkflow = True

        self._agent = AgentManager.CreateAgent(modelName, agentConfig)
        self._renderer = CliRenderer(self._config)
        self._registry = CliCommandRegistry()
        self._state = ECliState.IDLE
        self._cancellationToken: Optional[CancellationToken] = None
        self._messageQueue: asyncio.Queue[str] = asyncio.Queue()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        # 订阅渲染器到 Agent 事件总线
        self._agent.GetComponent(EventBusComponent).AddListener(self._renderer.OnEvent)

        # 注册内置指令
        RegisterBuiltinCommands(self._registry)

    # ---- 同步入口 ----

    def Run(self) -> None:
        """同步入口，内部启动 asyncio 事件循环。"""
        try:
            asyncio.run(self.RunAsync())
        except KeyboardInterrupt:
            print()

    # ---- 异步入口 ----

    async def RunAsync(self) -> None:
        """异步启动 REPL 主循环。

        启动 daemon 线程持续读取 stdin，与 Agent 执行并发运行。
        Agent 执行期间用户输入自动进入消息队列，
        当前轮结束后依次处理队列中的消息。
        """
        Logger.SetLevel(logging.WARNING)  # CLI 模式下抑制 INFO 日志，仅保留告警/错误
        self._EnsureUtf8Stdout()
        self._PrintBanner()

        # 保存事件循环引用，供 _InputThreadFunc 跨线程调度
        self._loop = asyncio.get_running_loop()

        # 安装统一 SIGINT 处理器（根据状态分流：RUNNING→取消 / IDLE→退出）
        signal.signal(signal.SIGINT, self._OnInterrupt)

        # 启动 daemon 线程持续读取 stdin（daemon 保证主线程退出时不阻塞）
        readerThread = threading.Thread(target=self._InputThreadFunc, daemon=True)
        readerThread.start()

        try:
            while self._state != ECliState.EXITING:
                self._PrintPrompt()
                userInput = await self._messageQueue.get()
                if not userInput:
                    continue

                if userInput.startswith('/'):
                    await self._HandleCommandAsync(userInput)
                else:
                    await self._RunAgentAsync(userInput)
                    # Agent 执行完毕后，排空在此期间入队的消息
                    await self._DrainQueueAsync()
        finally:
            pass

        self._PrintGoodbye()

    # ---- 输入线程 ----

    def _InputThreadFunc(self) -> None:
        """Daemon 线程：阻塞式读取 stdin，通过 run_coroutine_threadsafe 入队。

        使用 sys.stdin.readline() 替代 input()，避免 input() 的 prompt 参数
        在 Agent 流式输出期间在终端打印多余提示符。
        """
        loop = self._loop
        while True:
            try:
                line = sys.stdin.readline()
                if not line:  # EOF (Ctrl+Z on Windows, Ctrl+D on Unix)
                    loop.call_soon_threadsafe(self._messageQueue.put_nowait, '/exit')
                    break
                line = line.rstrip('\n\r')
                if line:
                    loop.call_soon_threadsafe(self._messageQueue.put_nowait, line)
            except Exception:
                break

    # ---- 队列排空 ----

    async def _DrainQueueAsync(self) -> None:
        """排空消息队列中等待处理的消息。

        Agent 执行期间用户可能输入了多条消息，此方法依次处理。
        处理期间用户仍可继续输入，新消息将在下一轮被处理。
        """
        while not self._messageQueue.empty():
            userInput = self._messageQueue.get_nowait()
            if not userInput:
                continue
            if userInput.startswith('/'):
                await self._HandleCommandAsync(userInput)
            else:
                await self._RunAgentAsync(userInput)

    # ---- 指令分发 ----

    async def _HandleCommandAsync(self, userInput: str) -> None:
        """解析并分发斜杠指令，处理 exit 请求。"""
        ctx = CliContext(self._agent, self._config, self._renderer, self._registry)
        handled = await self._registry.DispatchAsync(userInput, ctx)
        if handled and ctx.WantsExit:
            self._state = ECliState.EXITING

    # ---- Agent 执行 ----

    async def _RunAgentAsync(self, message: str) -> None:
        """启动 Agent 流式执行。"""
        self._cancellationToken = CancellationToken()
        self._state = ECliState.RUNNING

        try:
            await self._agent.RunStreamAsync(message, self._cancellationToken)
        except Exception:
            traceback.print_exc()
        finally:
            self._state = ECliState.IDLE
            self._cancellationToken = None

        # 本轮用量页脚
        self._PrintUsageFooter()

    # ---- 信号处理 ----

    def _OnInterrupt(self, signum: int, frame: object) -> None:
        """统一 SIGINT 处理器，根据当前状态分流。

        - RUNNING: 首次触发取消 token，Agent 优雅退出。
        - CANCELLING: 二次触发强制退出。
        - IDLE: 直接退出 REPL。
        """
        if self._state == ECliState.RUNNING:
            if self._cancellationToken is not None and not self._cancellationToken.IsCancellationRequested:
                self._state = ECliState.CANCELLING
                self._cancellationToken.Cancel()
                c = self._config
                sys.stdout.write(f"\n{c.Color('[Cancelling...]', c.AMBER)}\n")
                sys.stdout.flush()
        elif self._state == ECliState.CANCELLING:
            c = self._config
            sys.stdout.write(f"\n{c.Color('[Force exit]', c.RED)}\n")
            sys.stdout.flush()
            self._state = ECliState.EXITING
            self._WakeUpMainLoop()
        else:
            # IDLE 状态下 Ctrl+C 退出
            self._state = ECliState.EXITING
            self._WakeUpMainLoop()

    def _WakeUpMainLoop(self) -> None:
        """向消息队列放入空串唤醒主循环（使其从 queue.get() 中解挂）。"""
        self._messageQueue.put_nowait('')

    # ---- Banner / Prompt / Goodbye ----

    def _PrintBanner(self) -> None:
        """打印 CLI 欢迎横幅。"""
        modelName = self._agent.GetComponent(LLMComponent).modelName
        sessionId = self._agent.GetComponent(SessionComponent).ActiveSessionId
        self._renderer.PrintBanner(modelName, sessionId)

    def _PrintGoodbye(self) -> None:
        """打印退出信息。"""
        c = self._config
        sys.stdout.write(c.Dim(f"\n  {c.BOX_BL}{c.BOX_H * 20} See you {c.BOX_BR}\n\n"))
        sys.stdout.flush()

    def _PrintPrompt(self) -> None:
        """打印 REPL 提示符。

        IDLE 时显示紫色箭头，RUNNING 时不显示提示符
        （用户可直接输入，消息自动入队）。
        """
        if self._state != ECliState.IDLE:
            return
        c = self._config
        sys.stdout.write(f"{c.Color(c.ICON_PROMPT, c.PURPLE)} ")
        sys.stdout.flush()

    def _PrintUsageFooter(self) -> None:
        """打印本轮 Token 用量页脚。"""
        if not self._config.showTokenUsage:
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
