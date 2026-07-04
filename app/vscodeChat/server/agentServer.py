"""agentServer —— stdin/stdout JSON Lines Agent 服务进程。

由 VSCode 扩展通过 child_process 启动，stdin/stdout 承载 JSON Lines 协议，
stderr 用于日志输出。复用 CLI Agent 架构（AgentManager + Agent.RunStreamAsync），
不依赖 CliRenderer/CliApp 的终端渲染。

Usage:
    python agentServer.py          # 阻塞运行，stdin 读命令，stdout 写事件
"""

from __future__ import annotations

import asyncio
import json
import sys
import traceback
from typing import Optional

# 确保项目根目录在 path 中
import os as _os
_PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))))
sys.path.insert(0, _PROJECT_ROOT)
_os.chdir(_PROJECT_ROOT)

from agent import AgentManager
from agent.component.eventBus.agentStreamEvent import AgentStreamEvent, EAgentStreamEventType
from agent.component.eventBus.eventBusComponent import EventBusComponent
from agent.component.llm.llmComponent import LLMComponent
from agent.component.session.sessionComponent import SessionComponent
from agent.component.tool.toolResult import ToolResult

from common.cancellationToken import CancellationToken
from common.logger import Logger

import logging as _logging
Logger.SetLevel(_logging.WARNING)


class AgentServer:
    """stdin/stdout JSON Lines Agent 服务器。

    读取 stdin 的 JSON 命令，将 Agent 事件以 JSON Lines 格式写入 stdout。
    stderr 仅用于内部日志（不影响协议流）。

    协议：
        上行（stdin）: {"type":"chat","message":"...","model":"..."}
        下行（stdout）: {"type":"text_delta","turn":0,"text":"..."}
    """

    def __init__(self) -> None:
        self._agent = None
        self._cancellationToken: Optional[CancellationToken] = None
        self._currentModel: str = ""
        self._handlerTask: Optional[asyncio.Task] = None

    # ---- 入口 ----

    async def RunAsync(self) -> None:
        """主循环：从 stdin 逐行读取 JSON 命令，异步分发处理。"""
        loop = asyncio.get_running_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)

        await loop.connect_read_pipe(lambda: protocol, sys.stdin)

        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                lineStr = line.decode("utf-8").strip()
                if not lineStr:
                    continue
                try:
                    cmd = json.loads(lineStr)
                except json.JSONDecodeError:
                    self._WriteLog(f"Invalid JSON: {lineStr[:100]}")
                    continue
                await self._DispatchAsync(cmd)
        except asyncio.CancelledError:
            pass

    # ---- 命令分发 ----

    async def _DispatchAsync(self, cmd: dict) -> None:
        cmdType = cmd.get("type", "")
        if cmdType == "chat":
            await self._HandleChatAsync(cmd.get("message", ""), cmd.get("model", ""))
        elif cmdType == "cancel":
            self._HandleCancel()
        elif cmdType == "switchModel":
            self._HandleSwitchModel(cmd.get("model", ""))
        elif cmdType == "clear":
            await self._HandleClearAsync()
        elif cmdType == "ping":
            self._WriteStdout({"type": "pong"})
        else:
            self._WriteLog(f"Unknown command: {cmdType}")

    # ---- Chat ----

    async def _HandleChatAsync(self, message: str, model: str) -> None:
        """启动 Agent ReAct 流式执行。"""
        if not message.strip():
            self._WriteStdout({"type": "error", "msg": "Empty message"})
            return

        # 模型变更时重建 Agent
        if self._agent is None or (model and model != self._currentModel):
            try:
                self._agent = AgentManager.CreateAgent(model or None)
                self._currentModel = model or self._agent.GetComponent(LLMComponent).modelName
            except Exception as exc:
                self._WriteStdout({"type": "error", "msg": f"Failed to create agent with model '{model}': {exc}"})
                return

            # 订阅事件
            self._agent.GetComponent(EventBusComponent).AddListener(self._OnAgentEvent)

        self._cancellationToken = CancellationToken()

        try:
            await self._agent.RunStreamAsync(message, self._cancellationToken)
        except Exception:
            traceback.print_exc(file=sys.stderr)

    # ---- Cancel ----

    def _HandleCancel(self) -> None:
        """取消当前 Agent 执行。"""
        if self._cancellationToken is not None:
            self._cancellationToken.Cancel()
            self._WriteLog("Cancel requested")

    # ---- Switch Model ----

    def _HandleSwitchModel(self, model: str) -> None:
        """切换到指定模型，重建 Agent。"""
        if not model:
            return
        try:
            # 先取消当前执行
            if self._cancellationToken is not None:
                self._cancellationToken.Cancel()

            newAgent = AgentManager.CreateAgent(model)
            newAgent.GetComponent(EventBusComponent).AddListener(self._OnAgentEvent)
            self._agent = newAgent
            self._currentModel = model
            self._WriteStdout({
                "type": "model_switched",
                "model": _ModelShortName(model),
                "fullName": newAgent.GetComponent(LLMComponent).modelName,
            })
        except Exception as exc:
            self._WriteStdout({"type": "error", "msg": f"Failed to switch to '{model}': {exc}"})

    # ---- Clear ----

    async def _HandleClearAsync(self) -> None:
        """清空当前会话上下文。"""
        if self._agent is None:
            return
        sessionComp = self._agent.GetComponent(SessionComponent)
        newId = sessionComp.NewSession()
        self._WriteStdout({"type": "cleared", "sessionId": newId})

    # ---- Agent 事件回调 ----

    def _OnAgentEvent(self, event: AgentStreamEvent) -> None:
        """EventBusComponent 回调：将 AgentStreamEvent 转为 JSON 写入 stdout。

        此回调在 Push 流程中被同步调用，返回后 event 会被归还对象池，
        因此必须在回调内完成所有数据提取和输出。
        """
        et = event.eventType
        turn = event.turnIndex

        if et == EAgentStreamEventType.TURN_START:
            self._WriteStdout({"type": "turn_start", "turn": turn})

        elif et == EAgentStreamEventType.THINKING_DELTA:
            self._WriteStdout({"type": "thinking_delta", "turn": turn, "text": event.content})

        elif et == EAgentStreamEventType.THINKING_COMPLETE:
            self._WriteStdout({"type": "thinking_complete", "turn": turn, "text": event.content})

        elif et == EAgentStreamEventType.TEXT_DELTA:
            self._WriteStdout({"type": "text_delta", "turn": turn, "text": event.content})

        elif et == EAgentStreamEventType.TEXT_COMPLETE:
            self._WriteStdout({"type": "text_complete", "turn": turn, "text": event.content})

        elif et == EAgentStreamEventType.TOOL_START:
            self._WriteStdout({
                "type": "tool_start", "turn": turn,
                "toolName": event.toolName,
                "args": event.toolArgs or {},
            })

        elif et == EAgentStreamEventType.TOOL_RESULT:
            result: Optional[ToolResult] = event.toolResult
            isSuccess = result.success if result is not None else True
            content = event.content
            if len(content) > 500:
                content = content[:500] + "..."
            self._WriteStdout({
                "type": "tool_result", "turn": turn,
                "toolName": event.toolName,
                "content": content,
                "success": isSuccess,
            })

        elif et == EAgentStreamEventType.STATE_CHANGE:
            state = event.state
            self._WriteStdout({
                "type": "state_change", "turn": turn,
                "state": state.name if state is not None else "UNKNOWN",
            })

        elif et == EAgentStreamEventType.COMPACTION:
            self._WriteStdout({
                "type": "compaction", "turn": turn,
                "tokenSaved": event.tokenSaved,
                "compactedCount": event.compactedCount,
                "content": event.content,
            })

        elif et == EAgentStreamEventType.ERROR:
            self._WriteStdout({
                "type": "error", "turn": turn,
                "msg": event.error or "Unknown error",
            })

        elif et == EAgentStreamEventType.DONE:
            # 尝试获取用量信息
            usage = {"type": "done"}
            if self._agent is not None:
                try:
                    llmComp = self._agent.GetComponent(LLMComponent)
                    usage["promptTokens"] = llmComp.LastPromptTokens
                    usage["completionTokens"] = llmComp.LastCompletionTokens
                    usage["cacheHitRate"] = llmComp.LastCacheHitRate
                except Exception:
                    pass
            self._WriteStdout(usage)

    # ---- 底层输出 ----

    def _WriteStdout(self, data: dict) -> None:
        """将 dict 序列化为 JSON 行写入 stdout。"""
        try:
            line = json.dumps(data, ensure_ascii=False)
            sys.stdout.write(line + "\n")
            sys.stdout.flush()
        except Exception:
            pass

    def _WriteLog(self, msg: str) -> None:
        """将日志写入 stderr。"""
        print(f"[agentServer] {msg}", file=sys.stderr, flush=True)


def _ModelShortName(modelKey: str) -> str:
    """从模型配置键提取缩略名。"""
    parts = modelKey.split("-")
    if len(parts) >= 2:
        return parts[0][:2].upper() + "-" + parts[1][:1].upper()
    return modelKey[:4].upper()


# ---- 主入口 ----

if __name__ == "__main__":
    server = AgentServer()
    try:
        asyncio.run(server.RunAsync())
    except KeyboardInterrupt:
        pass
