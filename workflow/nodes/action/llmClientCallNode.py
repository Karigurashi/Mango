"""LLM 对话调用节点 —— 通过 LLMClient 调用大模型并返回回复。"""

from common.const import ERole
from llm import LLMManager
from llm.provider.chatMessage import ChatMessage

from ...core.baseNode import BaseNode, handler
from ...core.eNodeCategory import ENodeCategory
from ...core.eStreamEventType import EStreamEventType
from ...core.nodeRegistry import NodeRegistry


@NodeRegistry.Register
class LLMClientCallNode(BaseNode):
    """LLM 对话调用 —— 使用 SystemPrompt + UserMessage 构建消息，调用指定模型。

    Config:
        ModelName: 模型名称（如 "deepseek-high"），为空则用默认模型。
        SystemPrompt: 系统提示词。
        UserMessage: 首轮用户消息（仅无上游时生效）。
        Temperature: 采样温度，默认 0.7。
        EnableThinking: 是否开启思考链（Anthropic Extended Thinking），默认关闭。

    节点间消息格式::

        {"role": "user", "content": "..."}

    下游 LLMCall 会将 role + content 原样写入对话历史，不做合并。
    """

    nodeType = "Action/LLMClientCall"
    category = ENodeCategory.ACTION
    displayName = "LLM Call"
    description = "调用大模型对话，返回生成文本"

    def __init__(self, **config) -> None:
        super().__init__(**config)
        self._history: list[ChatMessage] = []

    @classmethod
    def GetConfigSchema(cls) -> list[dict]:
        return [
            {"name": "ModelName", "type": "string", "default": "", "description": "模型名称（空=默认）"},
            {"name": "SystemPrompt", "type": "string", "default": "", "description": "系统提示词"},
            {"name": "UserMessage", "type": "string", "default": "", "description": "首轮用户消息（无上游时）"},
            {"name": "Temperature", "type": "number", "default": 0.7, "description": "采样温度（0-2），越高越随机"},
            {"name": "EnableThinking", "type": "boolean", "default": False, "description": "是否开启思考链（Anthropic Extended Thinking）"},
        ]

    @handler
    async def Handle(self, message) -> None:
        """默认入口：BeginPlay 传 None，使用节点配置的 UserMessage。"""
        userMessage = getattr(self, "UserMessage", "") or "hello"
        self._history.append(ChatMessage.User(userMessage))
        systemPrompt = getattr(self, "SystemPrompt", "") or ""
        await self._CallLLMAsync(systemPrompt)

    @handler(inputType=dict)
    async def HandleDict(self, message: dict) -> None:
        if message is None:
            await self.Handle(message)
            return
        content = message.get("content") or message.get("userMessage") or "hello"
        self._history.append(ChatMessage.User(content))
        systemPrompt = message.get("systemPrompt") or getattr(self, "SystemPrompt", "") or ""
        await self._CallLLMAsync(systemPrompt)

    @handler(inputType=str)
    async def HandleStr(self, message: str) -> None:
        self._history.append(ChatMessage.User(message))
        systemPrompt = getattr(self, "SystemPrompt", "") or ""
        await self._CallLLMAsync(systemPrompt)

    async def _CallLLMAsync(self, systemPrompt: str) -> None:
        """核心逻辑：构建消息、流式调用 LLM、写回上下文。"""
        modelName = getattr(self, "ModelName", "") or None
        temperature = float(getattr(self, "Temperature", 0.7) or 0.7)
        enableThinking = bool(getattr(self, "EnableThinking", False))

        client = LLMManager.GetClient(modelName)

        messages: list[ChatMessage] = []
        if systemPrompt:
            messages.append(ChatMessage.System(systemPrompt))
        messages.extend(self._history)

        cancellationToken = self.context.CancellationToken
        streamKwargs: dict = {"cancellationToken": cancellationToken}
        if enableThinking:
            streamKwargs["enableThinking"] = True

        fullContent = ""
        streamCallback = self.context.OnNodeStreamAsync
        nodeId = self.context.CurrentNodeId
        executionRound = self.context.ExecutionRound
        async for chunk in client.StreamAsync(
            messages,
            temperature=temperature,
            **streamKwargs,
        ):
            if chunk.content:
                fullContent += chunk.content
                if streamCallback is not None:
                    await streamCallback(
                        nodeId,
                        EStreamEventType.CONTENT,
                        {"text": chunk.content, "round": executionRound},
                    )
            if chunk.reasoningContent:
                if streamCallback is not None and enableThinking:
                    await streamCallback(
                        nodeId,
                        EStreamEventType.THINKING,
                        {"text": chunk.reasoningContent, "round": executionRound},
                    )
            if chunk.usage:
                if streamCallback is not None:
                    await streamCallback(
                        nodeId,
                        EStreamEventType.USAGE,
                        {
                            "promptTokens": chunk.usage.promptTokens,
                            "completionTokens": chunk.usage.completionTokens,
                            "round": executionRound,
                        },
                    ) 

        if streamCallback is not None:
            await streamCallback(nodeId, EStreamEventType.DONE, {"round": executionRound})

        self._history.append(ChatMessage.Assistant(fullContent))

        self.context.Set(f"{nodeId}.Response", fullContent)

        await self.context.SendMessageAsync({"content": fullContent})
