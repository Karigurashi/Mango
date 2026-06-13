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
from workflow.core.eExecutionStatus import EExecutionStatus
from workflow.core.eStreamEventType import EStreamEventType
from workflow.core.nodeRegistry import NodeRegistry
from workflow.core.workflowContext import NodeStreamCallback

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

        async def onNodeEvent(nodeId: int, status: EExecutionStatus):
            await queue.put({"type": "node", "nodeId": nodeId, "status": status.name.lower()})

        async def onNodeStream(nodeId: int, eventType: EStreamEventType, data: dict):
            await queue.put({"type": "stream", "nodeId": nodeId, "eventType": eventType.name.lower(), "data": data})

        def addLog(level: str, msg: str):
            asyncio.ensure_future(queue.put({"type": "log", "level": level, "msg": msg}))

        async def runWf():
            try:
                addLog("info", f"工作流 '{wfJson['name']}' 开始执行 — {len(req.nodes)} 个节点, {len(edgeData)} 条连线")

                wf = Workflow.FromJson(wfJson)
                entryNodes = wf.graph.GetEntryNodes()
                addLog("info", f"入口节点: {entryNodes if entryNodes else '无'}")

                start = time.perf_counter()
                ctx = await wf.ExecuteAsync(
                    onNodeEvent=onNodeEvent,
                    onNodeStream=onNodeStream,
                    cancellationToken=cancellationToken,
                )
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8765)
