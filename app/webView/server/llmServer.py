"""LLM Chat API 后端 —— FastAPI 服务，对接 LLMManager 和 Workflow 执行引擎。"""

import sys
import os
import time
import json
import asyncio

# 确保项目根目录在 path 中，且工作目录在项目根
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from llm import LLMManager
from common.cancellationToken import CancellationToken
from llm.provider.chatMessage import ChatMessage
from llm.llmRequestParams import LLMRequestParams
from workflow import Workflow, WorkflowContext
from workflow.core.workflowExecutor import WorkflowExecutor
from workflow.core.workflowStreamEvent import EStreamEventType, WorkflowStreamEvent
from workflow.core.nodeRegistry import NodeRegistry
from workflow.core.workflowEventBus import WorkflowEventBus

from agent import Agent
from agent.component.eventBus.agentStreamEvent import AgentStreamEvent, EAgentStreamEventType
from agent.component.eventBus.eventBusComponent import EventBusComponent
from agent.component.data.agentConfig import AgentConfig
from agent.component.data.eAgentState import EAgentState

app = FastAPI(title="Workflow LLM Chat API")

# 允许前端跨域请求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    systemPrompt: str = ""
    userMessage: str = ""
    modelName: str = ""
    temperature: float = 0.7
    maxTokens: int = 256


class ChatResponse(BaseModel):
    content: str
    reasoningContent: str = ""
    promptTokens: int = 0
    completionTokens: int = 0
    modelName: str = ""


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/nodes")
async def list_nodes():
    """返回所有已注册的工作流节点定义（从 Python NodeRegistry 实时获取）。"""
    return {"nodes": NodeRegistry.GetAllNodeInfo()}


@app.get("/api/models")
async def list_models():
    """返回可用模型列表。"""
    try:
        models = LLMManager.ListModels()
        default = LLMManager.DefaultModel()
        return {"models": models, "default": default}
    except Exception as e:
        return {"models": [], "default": "", "error": str(e)}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """处理对话请求，调用 LLM 返回回复。"""
    # 确定模型名并获取 Provider
    provider = LLMManager.GetProvider(req.modelName or None)

    # 构建消息
    messages = []
    if req.systemPrompt:
        messages.append(ChatMessage.System(req.systemPrompt))
    messages.append(ChatMessage.User(req.userMessage or "Hello"))

    # 调用
    response = await provider.InvokeAsync(
        messages,
        requestParams=LLMRequestParams(
            temperature=req.temperature,
            maxTokens=req.maxTokens,
        ),
    )

    return ChatResponse(
        content=response.content or "",
        reasoningContent=response.reasoningContent or "",
        promptTokens=response.usage.promptTokens if response.usage else 0,
        completionTokens=response.usage.completionTokens if response.usage else 0,
        modelName=modelName,
    )


@app.post("/api/chat/stream")
async def chatStream(req: ChatRequest):
    """流式对话端点 —— 通过 SSE 实时推送 LLM 回复增量。

    事件格式:
        {"type": "thinking", "data": {"text": "..."}}
        {"type": "content", "data": {"text": "..."}}
        {"type": "usage", "data": {"promptTokens": 123, "completionTokens": 456}}
        {"type": "done", "data": {"finishReason": "stop"}}
        {"type": "error", "data": {"msg": "..."}}

    事件类型 see: EStreamEventType 枚举
    """
    provider = LLMManager.GetProvider(req.modelName or None)

    messages = []
    if req.systemPrompt:
        messages.append(ChatMessage.System(req.systemPrompt))
    messages.append(ChatMessage.User(req.userMessage or "Hello"))

    cancellationToken = CancellationToken()

    async def generate():
        try:
            async for chunk in provider.StreamAsync(
                messages,
                requestParams=LLMRequestParams(
                    temperature=req.temperature,
                    maxTokens=req.maxTokens,
                ),
                cancellationToken=cancellationToken,
            ):
                if chunk.content:
                    yield f"data: {json.dumps({'type': 'content', 'data': {'text': chunk.content}}, ensure_ascii=False)}\n\n"
                if chunk.reasoningContent:
                    yield f"data: {json.dumps({'type': 'thinking', 'data': {'text': chunk.reasoningContent}}, ensure_ascii=False)}\n\n"
                if chunk.usage:
                    yield f"data: {json.dumps({'type': 'usage', 'data': {'promptTokens': chunk.usage.promptTokens, 'completionTokens': chunk.usage.completionTokens}}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'data': {'finishReason': 'stop'}}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'data': {'msg': str(e)}}, ensure_ascii=False)}\n\n"
        finally:
            cancellationToken.Cancel()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


class RunRequest(BaseModel):
    """工作流执行请求 —— 与前端 flowToJson 输出格式一致。"""
    name: str = ""
    nodes: list[dict] = []
    edges: list[dict] = []
    connections: list[dict] = []  # 向后兼容


class RunResponse(BaseModel):
    success: bool
    log: list[dict]  # [{type: str, msg: str}]
    blackboard: dict[str, object] = {}
    error: str = ""


@app.post("/api/run/stream")
async def run_workflow_stream(req: RunRequest):
    """通过 SSE 实时推送工作流执行过程（节点状态事件 + 日志 + LLM 流式输出）。

    事件格式:
        {"type": "workflow", "status": "running"|"completed"|"failed"|"cancelled"}
        {"type": "node", "nodeId": 1, "status": "running"|"completed"|"failed"|"cancelled"}
        {"type": "log", "level": "info"|"error"|"action"|"llm"|"response", "msg": "..."}
        {"type": "stream", "nodeId": 1, "eventType": "thinking"|"content"|"usage"|"done", "data": {...}}
        {"type": "done", "success": true, "blackboard": {...}}
        {"type": "cancelled", "msg": "..."}
        {"type": "error", "msg": "..."}

    流式事件类型 see: EStreamEventType 枚举

    客户端断开连接时，后台工作流任务会被自动取消。
    """
    wfTask: asyncio.Task | None = None
    cancellationToken = CancellationToken()

    async def eventGenerator():
        nonlocal wfTask, cancellationToken
        queue: asyncio.Queue = asyncio.Queue()
        wfJson: dict = {"name": req.name or "WebWorkflow"}
        wfJson["nodes"] = req.nodes
        edgeData = req.edges if req.edges else req.connections
        wfJson["edges"] = edgeData

        def onStreamEvent(event: WorkflowStreamEvent):
            if event.eventType == EStreamEventType.NODE_STATUS:
                queue.put_nowait({
                    "type": "node",
                    "nodeId": event.nodeId,
                    "status": event.status.name if event.status else "",
                })
            else:
                queue.put_nowait({
                    "type": "stream",
                    "nodeId": event.nodeId,
                    "agentId": event.agentId,
                    "eventType": event.eventType.name.lower(),
                    "text": event.message,
                })

        def addLog(level: str, msg: str):
            asyncio.ensure_future(queue.put({"type": "log", "level": level, "msg": msg}))

        async def runWf():
            try:
                addLog("info", f"工作流 '{wfJson['name']}' 开始执行 — {len(req.nodes)} 个节点, {len(edgeData)} 条连线")

                wf = Workflow.FromJson(wfJson)
                entryNodes = wf.graph.GetEntryNodes()
                addLog("info", f"入口节点: {entryNodes if entryNodes else '无'}")

                # 创建工作流事件总线并订阅同步回调
                eventBus = WorkflowEventBus()
                eventBus.AddListener(onStreamEvent)

                ctx = WorkflowContext()
                start = time.perf_counter()
                ctx = await WorkflowExecutor.ExecuteAsync(wf, ctx, eventBus, cancellationToken)
                elapsed = time.perf_counter() - start
                addLog("info", f"执行完成，耗时 {elapsed:.2f}s")

                # 收集结果
                allKeys = ctx.GetAll()
                bbResult: dict = {}
                for key, value in sorted(allKeys.items()):
                    if value is None:
                        continue
                    bbResult[key] = value
                    if key.startswith("var."):
                        addLog("action", f"📝 变量 {key[4:]} = {_fmtValue(value)}")
                    if "." in key and not key.startswith("var."):
                        nid, pinName = key.rsplit(".", 1)
                        if pinName == "Response":
                            addLog("response", f"💬 [{nid}] LLM 回复: {_fmtValue(value, 200)}")
                        elif pinName == "ReasoningContent" and value:
                            addLog("llm", f"💭 [{nid}] 思考链: {_fmtValue(value, 150)}")
                        elif pinName == "PromptTokens":
                            completion = allKeys.get(f"{nid}.CompletionTokens", "?")
                            addLog("llm", f"📊 [{nid}] Token: in={value} out={completion}")

                addLog("info", f"上下文共 {len(bbResult)} 个有效键值")
                await queue.put({"type": "done", "success": True, "blackboard": bbResult})
            except asyncio.CancelledError:
                # 被外部取消
                await queue.put({"type": "cancelled", "msg": "工作流已被中断"})
            except Exception as e:
                addLog("error", f"执行失败: {e}")
                import traceback
                traceback.print_exc()
                await queue.put({"type": "error", "msg": str(e)})

        wfTask = asyncio.create_task(runWf())

        try:
            while True:
                event = await queue.get()
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event["type"] in ("done", "error", "cancelled"):
                    break
        finally:
            # 双保险取消：先 Cancel Token（通知底层 LLM 关闭连接），再 Cancel Task
            cancellationToken.Cancel()
            if wfTask and not wfTask.done():
                wfTask.cancel()
                try:
                    await wfTask
                except asyncio.CancelledError:
                    pass

    return StreamingResponse(
        eventGenerator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/run", response_model=RunResponse)
async def run_workflow(req: RunRequest):
    """执行工作流并返回执行日志和上下文结果。"""
    log: list[dict] = []
    t0 = time.perf_counter()

    def addLog(typ: str, msg: str):
        log.append({"type": typ, "msg": msg})

    try:
        # 构建工作流 JSON（兼容 connections 和 edges 两种字段名）
        wfJson: dict = {"name": req.name or "WebWorkflow"}
        wfJson["nodes"] = req.nodes
        edgeData = req.edges if req.edges else req.connections
        wfJson["edges"] = edgeData

        addLog("info", f"工作流 '{wfJson['name']}' 开始执行 — {len(req.nodes)} 个节点, {len(edgeData)} 条连线")

        # 创建工作流并执行
        wf = Workflow.FromJson(wfJson)

        entryNodes = wf.graph.GetEntryNodes()
        addLog("info", f"入口节点: {entryNodes if entryNodes else '无'}")

        start = time.perf_counter()
        ctx = await wf.ExecuteAsync()
        elapsed = time.perf_counter() - start
        addLog("info", f"执行完成，耗时 {elapsed:.2f}s")

        # 收集结果
        allKeys = ctx.GetAll()
        bbResult: dict[str, object] = {}

        for key, value in sorted(allKeys.items()):
            if value is None:
                continue
            bbResult[key] = value

            # 变量
            if key.startswith("var."):
                varName = key[4:]
                addLog("action", f"📝 变量 {varName} = {_fmtValue(value)}")

            # 节点输出
            if "." in key and not key.startswith("var."):
                nodeId, pinName = key.rsplit(".", 1)
                if pinName == "Response":
                    addLog("response", f"💬 [{nodeId}] LLM 回复: {_fmtValue(value, 200)}")
                elif pinName == "ReasoningContent" and value:
                    addLog("llm", f"💭 [{nodeId}] 思考链: {_fmtValue(value, 150)}")
                elif pinName == "PromptTokens":
                    completion = allKeys.get(f"{nodeId}.CompletionTokens", "?")
                    addLog("llm", f"📊 [{nodeId}] Token: in={value} out={completion}")

        addLog("info", f"上下文共 {len(bbResult)} 个有效键值")
        elapsedTotal = time.perf_counter() - t0
        addLog("info", f"请求总耗时 {elapsedTotal:.2f}s")

        return RunResponse(success=True, log=log, blackboard=bbResult)

    except Exception as e:
        addLog("error", f"执行失败: {e}")
        import traceback
        traceback.print_exc()
        return RunResponse(success=False, log=log, error=str(e))


def _fmtValue(value, maxLen: int = 100) -> str:
    """格式化值为可读字符串。"""
    s = str(value)
    if len(s) > maxLen:
        return s[:maxLen] + "..."
    return s


# ============================================================
# Agent Chat API —— 对接 Agent 框架
# ============================================================

class AgentManager:
    """Agent 单例管理器，维持跨请求的 Agent 实例与会话状态。"""

    _instance: "AgentManager | None" = None

    def __init__(self) -> None:
        self._agent: Agent | None = None
        self._config: AgentConfig = AgentConfig.Default()

    @classmethod
    def Get(cls) -> "AgentManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def GetAgentAsync(self, modelName: str = "") -> Agent:
        """获取或创建 Agent 实例。modelName 变化时重建。"""
        provider = LLMManager.GetProvider(modelName or None)
        if self._agent is None or self._agent._llmComponent.llm is not provider:
            if self._agent is not None:
                self._agent = None
            self._agent = Agent(provider, config=self._config)
        return self._agent

    def GetConfig(self) -> dict:
        return self._config.ToDict()

    def UpdateConfig(self, data: dict) -> None:
        self._config = AgentConfig.FromDict(data)
        self._agent = None  # 配置变更后重建 Agent

    def GetExtensions(self) -> dict:
        """获取当前 skills / rules / mcp / tools 信息。"""
        if self._agent is None:
            return {"skills": [], "rules": [], "mcp": [], "tools": []}
        try:
            from agent.component.skill.skillComponent import SkillComponent
            from agent.component.rule.ruleComponent import RuleComponent
            from agent.component.mcp.mcpComponent import McpComponent
            from agent.component.tool.toolComponent import ToolComponent

            skillComp = self._agent.GetComponent(SkillComponent)
            ruleComp = self._agent.GetComponent(RuleComponent)
            mcpComp = self._agent.GetComponent(McpComponent)
            toolComp = self._agent.GetComponent(ToolComponent)

            return {
                "skills": [{"name": s.name, "description": s.description, "autoInvokable": s.IsAutoInvokable()} for s in skillComp.GetAll().values()],
                "rules": [{"name": f"rule_{i}", "preview": r["body"][:100]} for i, r in enumerate(ruleComp.GetAll())],
                "mcp": [{"name": c.name, "transport": c.transport.value, "enabled": c.enabled} for c in mcpComp.GetAll().values()],
                "tools": [t.GetToolInfo() for t in toolComp.GetAll().values()],
            }
        except Exception:
            return {"skills": [], "rules": [], "mcp": [], "tools": []}

    def GetContextState(self) -> dict:
        """获取当前 context 组装状态。"""
        if self._agent is None:
            return {"messages": [], "estimatedTokens": 0, "turnIndex": 0, "compressedSummary": None, "stats": {}, "totalPromptTokens": 0, "totalCompletionTokens": 0}
        try:
            from agent.component.session.sessionComponent import SessionComponent

            sessionComp = self._agent.GetComponent(SessionComponent)

            messages = sessionComp.residentMessages + sessionComp.conversationMessages
            msgList = []
            for m in messages:
                entry = {
                    "messageId": str(m.messageId)[:8] + "...",
                    "role": str(m.role),
                    "content": m.content if m.content else "",
                    "lodLevel": m.lodLevel.name,
                    "isCompacted": False,
                    "isAgedOut": m.isAgedOut,
                }
                # 工具消息：暴露 toolCallId
                if m.chatMessage.toolCallId:
                    entry["toolCallId"] = m.chatMessage.toolCallId
                # assistant 消息：暴露工具调用列表
                if m.chatMessage.toolCalls:
                    entry["toolCalls"] = [
                        {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                        for tc in m.chatMessage.toolCalls
                    ]
                # cacheControl 标记
                if m.chatMessage.cacheControl:
                    entry["cacheControl"] = True
                msgList.append(entry)

            stats = sessionComp.GetStats()
            summary = None
            summaryMsg = next((m for m in messages if m.isSummary), None)
            if summaryMsg:
                summary = {"content": summaryMsg.content[:300], "upToTurn": -1}

            # 获取真实 token 用量
            totalPromptTokens = 0
            totalCompletionTokens = 0
            try:
                usage = self._agent._llmComponent.GetUsage()
                totalPromptTokens = usage.promptTokens
                totalCompletionTokens = usage.completionTokens
            except Exception:
                pass

            return {
                "messages": msgList,
                "estimatedTokens": self._agent._llmComponent.LastPromptTokens,
                "turnIndex": 0,
                "compressedSummary": summary,
                "stats": stats,
                "totalPromptTokens": totalPromptTokens,
                "totalCompletionTokens": totalCompletionTokens,
            }
        except Exception as e:
            return {"messages": [], "estimatedTokens": 0, "turnIndex": 0, "compressedSummary": None, "stats": {}, "totalPromptTokens": 0, "totalCompletionTokens": 0, "error": str(e)}

    def ClearContext(self) -> dict:
        """清空当前 Agent 上下文（创建新会话，保留系统规则）。"""
        if self._agent is None:
            return {"success": False, "error": "Agent 未初始化"}
        try:
            from agent.component.session.sessionComponent import SessionComponent
            sessionComp = self._agent.GetComponent(SessionComponent)
            sessionComp.NewSession()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}


class AgentChatRequest(BaseModel):
    userMessage: str
    modelName: str = ""


class AgentConfigUpdate(BaseModel):
    config: dict


@app.post("/api/agent/chat/stream")
async def agentChatStream(req: AgentChatRequest):
    """Agent ReAct 流式对话 —— 通过 SSE 实时推送所有 Agent 事件。

    事件格式:
        {"type": "turn_start", "turn": 0}
        {"type": "thinking_delta", "turn": 0, "text": "..."}
        {"type": "thinking_complete", "turn": 0, "text": "..."}
        {"type": "text_delta", "turn": 0, "text": "..."}
        {"type": "text_complete", "turn": 0, "text": "..."}
        {"type": "tool_start", "turn": 0, "toolName": "...", "args": {...}}
        {"type": "tool_result", "turn": 0, "toolName": "...", "content": "...", "success": true}
        {"type": "state_change", "state": "THINKING", "turn": 0}
        {"type": "usage", "turn": 0, "promptTokens": 123, "completionTokens": 456}
        {"type": "done"}
        {"type": "error", "msg": "..."}
    """
    manager = AgentManager.Get()
    cancellationToken = CancellationToken()

    async def generate():
        try:
            agent = await manager.GetAgentAsync(req.modelName)
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'msg': f'Failed to create agent: {e}'}, ensure_ascii=False)}\n\n"
            return

        # 订阅事件
        eventQueue: asyncio.Queue = asyncio.Queue()
        eventBusComp = agent.GetComponent(EventBusComponent)

        def onEvent(event: AgentStreamEvent):
            # 同步回调中立即拷贝数据，后续 Push 会 Release 事件
            data = {
                "eventType": event.eventType,
                "content": event.content,
                "toolName": event.toolName,
                "toolArgs": event.toolArgs,
                "toolResult": event.toolResult,
                "state": event.state,
                "turnIndex": event.turnIndex,
                "tokenSaved": event.tokenSaved,
                "compactedCount": event.compactedCount,
                "error": event.error,
            }
            try:
                eventQueue.put_nowait(data)
            except asyncio.QueueFull:
                pass

        eventBusComp.AddListener(onEvent)

        try:
            # 启动 Agent
            task = asyncio.create_task(agent.RunStreamAsync(req.userMessage, cancellationToken))

            lastUsagePrompt = 0
            lastUsageCompletion = 0
            lastUsageCacheRead = 0
            lastUsageCacheCreation = 0

            while True:
                try:
                    data: dict = await asyncio.wait_for(eventQueue.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    if task.done():
                        break
                    continue

                et = data["eventType"]
                turn = data["turnIndex"]

                if et == EAgentStreamEventType.TURN_START:
                    yield f"data: {json.dumps({'type': 'turn_start', 'turn': turn}, ensure_ascii=False)}\n\n"

                elif et == EAgentStreamEventType.THINKING_DELTA:
                    yield f"data: {json.dumps({'type': 'thinking_delta', 'turn': turn, 'text': data['content']}, ensure_ascii=False)}\n\n"

                elif et == EAgentStreamEventType.THINKING_COMPLETE:
                    yield f"data: {json.dumps({'type': 'thinking_complete', 'turn': turn, 'text': data['content']}, ensure_ascii=False)}\n\n"

                elif et == EAgentStreamEventType.TEXT_DELTA:
                    yield f"data: {json.dumps({'type': 'text_delta', 'turn': turn, 'text': data['content']}, ensure_ascii=False)}\n\n"

                elif et == EAgentStreamEventType.TEXT_COMPLETE:
                    yield f"data: {json.dumps({'type': 'text_complete', 'turn': turn, 'text': data['content']}, ensure_ascii=False)}\n\n"

                elif et == EAgentStreamEventType.TOOL_START:
                    yield f"data: {json.dumps({'type': 'tool_start', 'turn': turn, 'toolName': data['toolName'], 'args': data['toolArgs'] or {}}, ensure_ascii=False)}\n\n"

                elif et == EAgentStreamEventType.TOOL_RESULT:
                    result = data['toolResult']
                    isSuccess = result.success if result else True
                    yield f"data: {json.dumps({'type': 'tool_result', 'turn': turn, 'toolName': data['toolName'], 'content': data['content'][:500], 'success': isSuccess}, ensure_ascii=False)}\n\n"

                elif et == EAgentStreamEventType.STATE_CHANGE:
                    state = data['state']
                    stateName = state.name if state else 'UNKNOWN'
                    yield f"data: {json.dumps({'type': 'state_change', 'state': stateName, 'turn': turn}, ensure_ascii=False)}\n\n"

                    # 在 THINKING -> ACTING 转换时记录本轮 LLM 用量
                    if state == EAgentState.ACTING:
                        try:
                            usage = agent._llmComponent.GetUsage()
                            promptDelta = usage.promptTokens - lastUsagePrompt
                            completionDelta = usage.completionTokens - lastUsageCompletion
                            cacheReadDelta = usage.cacheReadInputTokens - lastUsageCacheRead
                            cacheCreationDelta = usage.cacheCreationInputTokens - lastUsageCacheCreation
                            lastUsagePrompt = usage.promptTokens
                            lastUsageCompletion = usage.completionTokens
                            lastUsageCacheRead = usage.cacheReadInputTokens
                            lastUsageCacheCreation = usage.cacheCreationInputTokens
                            if promptDelta > 0 or completionDelta > 0:
                                cacheHitRate = round(cacheReadDelta / promptDelta * 100, 1) if promptDelta > 0 else 0
                                yield f"data: {json.dumps({'type': 'usage', 'turn': turn, 'promptTokens': promptDelta, 'completionTokens': completionDelta, 'cacheReadInputTokens': cacheReadDelta, 'cacheCreationInputTokens': cacheCreationDelta, 'cacheHitRate': cacheHitRate}, ensure_ascii=False)}\n\n"
                        except Exception:
                            pass

                elif et == EAgentStreamEventType.COMPACTION:
                    yield f"data: {json.dumps({'type': 'compaction', 'turn': turn, 'tokenSaved': data.get('tokenSaved', 0), 'compactedCount': data.get('compactedCount', 0), 'content': data['content']}, ensure_ascii=False)}\n\n"

                elif et == EAgentStreamEventType.ERROR:
                    yield f"data: {json.dumps({'type': 'error', 'msg': data['error'], 'turn': turn}, ensure_ascii=False)}\n\n"

                elif et == EAgentStreamEventType.DONE:
                    # 最终用量
                    try:
                        usage = agent._llmComponent.GetUsage()
                        promptDelta = usage.promptTokens - lastUsagePrompt
                        completionDelta = usage.completionTokens - lastUsageCompletion
                        cacheReadDelta = usage.cacheReadInputTokens - lastUsageCacheRead
                        cacheCreationDelta = usage.cacheCreationInputTokens - lastUsageCacheCreation
                        if promptDelta > 0 or completionDelta > 0:
                            cacheHitRate = round(cacheReadDelta / promptDelta * 100, 1) if promptDelta > 0 else 0
                            yield f"data: {json.dumps({'type': 'usage', 'turn': turn, 'promptTokens': promptDelta, 'completionTokens': completionDelta, 'cacheReadInputTokens': cacheReadDelta, 'cacheCreationInputTokens': cacheCreationDelta, 'cacheHitRate': cacheHitRate}, ensure_ascii=False)}\n\n"
                    except Exception:
                        pass
                    yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
                    break

            if not task.done():
                await task

        except asyncio.CancelledError:
            pass
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'msg': str(e)}, ensure_ascii=False)}\n\n"
        finally:
            cancellationToken.Cancel()
            eventBusComp.RemoveListener(onEvent)
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/agent/config")
async def getAgentConfig():
    """获取当前 Agent 配置。"""
    manager = AgentManager.Get()
    return manager.GetConfig()


@app.post("/api/agent/config")
async def updateAgentConfig(req: AgentConfigUpdate):
    """更新 Agent 配置。"""
    manager = AgentManager.Get()
    try:
        manager.UpdateConfig(req.config)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/agent/extensions")
async def getAgentExtensions():
    """获取当前 Agent 的 skills / rules / mcp / tools 列表。"""
    manager = AgentManager.Get()
    # 确保 Agent 已初始化
    try:
        await manager.GetAgentAsync()
    except Exception:
        pass
    return manager.GetExtensions()


@app.post("/api/agent/context/clear")
async def clearAgentContext():
    """清空 Agent 上下文（创建新会话，保留系统规则）。"""
    manager = AgentManager.Get()
    return manager.ClearContext()


@app.get("/api/agent/context")
async def getAgentContext():
    """获取当前 context 组装状态（调试用）。"""
    manager = AgentManager.Get()
    return manager.GetContextState()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8765)
