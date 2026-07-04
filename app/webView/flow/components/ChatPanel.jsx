import { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';

export const API_BASE = 'http://127.0.0.1:8765';

/**
 * 对话面板 — 选中 LLM Call 节点后预览 System Prompt + User Message 的效果。
 */
export default function ChatPanel({ selectedNode }) {
  const [messages, setMessages] = useState([]);
  const [inputText, setInputText] = useState('');
  const [loading, setLoading] = useState(false);
  const chatEndRef = useRef(null);
  const abortRef = useRef(null);

  const isLLM = selectedNode?.data?.nodeType === 'Action/LLMClientCall';

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    return () => {
      if (abortRef.current) abortRef.current.abort();
    };
  }, []);

  const handleSend = async () => {
    if (!inputText.trim()) return;
    if (!isLLM) {
      setMessages((m) => [...m, { role: 'system', content: '请先选中一个 LLM Call 节点' }]);
      return;
    }

    const config = selectedNode.data.config || {};
    const systemPrompt = config.SystemPrompt || '';
    const userMessage = inputText;
    const msg = { role: 'user', content: userMessage };
    setMessages((m) => [...m, msg]);
    setInputText('');
    setLoading(true);

    // 添加占位的 assistant 消息用于流式追加
    setMessages((m) => [...m, { role: 'assistant', content: '', reasoningContent: '', showReasoning: true, promptTokens: 0, completionTokens: 0 }]);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const res = await fetch(`${API_BASE}/api/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          systemPrompt,
          userMessage,
          modelName: config.ModelName || '',
          temperature: config.Temperature ?? 0.7,
          maxTokens: config.MaxTokens ?? 256,
        }),
        signal: controller.signal,
      });

      if (!res.ok) {
        const errText = await res.text();
        throw new Error(`HTTP ${res.status}: ${errText}`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const jsonStr = line.slice(6);
          try {
            const event = JSON.parse(jsonStr);
            setMessages((m) => {
              const updated = [...m];
              const lastIdx = updated.length - 1;
              const last = updated[lastIdx];
              if (!last || last.role !== 'assistant') return updated;

              if (event.type === 'content') {
                updated[lastIdx] = { ...last, content: last.content + event.data.text };
              } else if (event.type === 'thinking') {
                updated[lastIdx] = { ...last, reasoningContent: (last.reasoningContent || '') + event.data.text };
              } else if (event.type === 'usage') {
                updated[lastIdx] = { ...last, promptTokens: event.data.promptTokens, completionTokens: event.data.completionTokens };
              }
              return updated;
            });
          } catch (parseErr) {
            // 忽略解析错误
          }
        }
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        setMessages((m) => {
          const updated = [...m];
          // 移除占位消息
          if (updated.length > 0 && updated[updated.length - 1].role === 'assistant' && !updated[updated.length - 1].content) {
            updated.pop();
          }
          updated.push({
            role: 'error',
            content: `❌ 调用失败：${err.message}\n\n请确认后端服务已启动：\`python server/llmServer.py\``,
          });
          return updated;
        });
      }
    } finally {
      setLoading(false);
      abortRef.current = null;
    }
  };

  return (
    <div style={styles.chatContainer}>
      <div style={styles.chatHeader}>
        {isLLM
          ? `🤖 ${selectedNode.data.config?.ModelName || 'LLM Call'} — 对话预览`
          : '💬 选中 LLM Call 节点后，可在此预览对话'}
      </div>

      {/* 消息列表 */}
      <div style={styles.chatMessages}>
        {messages.length === 0 && (
          <div style={styles.chatEmpty}>
            {isLLM
              ? '在此测试 System Prompt + User Message 的对话效果'
              : '请先在画布中选中一个 LLM Call 节点'}
          </div>
        )}
        {messages.map((msg, i) => (
          <div
            key={i}
            style={{
              ...styles.chatBubble,
              alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
              background: msg.role === 'user'
                ? '#1a332a'
                : msg.role === 'assistant'
                  ? '#1f2530'
                  : msg.role === 'error'
                    ? '#2e1a1c'
                    : '#1a1f2b',
              borderColor: msg.role === 'user'
                ? '#234d38'
                : msg.role === 'error'
                  ? '#f2555a44'
                  : '#252b36',
            }}
          >
            <div style={styles.chatRole}>
              {msg.role === 'user' ? '你' : msg.role === 'assistant' ? '助手' : msg.role === 'error' ? '错误' : '系统'}
            </div>
            {/* 思考过程（可折叠） */}
            {msg.role === 'assistant' && msg.reasoningContent && (
              <details style={{ marginBottom: 8 }} open={msg.showReasoning !== false}>
                <summary style={{ cursor: 'pointer', color: '#e6b450', fontWeight: 600, fontSize: 11, userSelect: 'none' }}>
                  💭 思考过程
                </summary>
                <div className="md-content" style={{ marginTop: 6, padding: '8px 10px', background: '#151a24', borderRadius: 6, border: '1px solid #2b2418', fontSize: 11, lineHeight: 1.6, color: '#8b919b', maxHeight: 240, overflowY: 'auto' }}>
                  <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>
                    {msg.reasoningContent}
                  </ReactMarkdown>
                </div>
              </details>
            )}
            {/* 正文 */}
            <div className="md-content" style={{ lineHeight: 1.6 }}>
              {msg.role === 'assistant' && !msg.content && loading ? (
                <span style={{ color: '#5a606b', fontStyle: 'italic' }}>思考中…</span>
              ) : (
                <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>
                  {msg.content}
                </ReactMarkdown>
              )}
            </div>
            {/* Token 用量 */}
            {msg.role === 'assistant' && (msg.promptTokens || msg.completionTokens) ? (
              <div style={{ marginTop: 8, fontSize: 10, color: '#5a606b', borderTop: '1px solid #1a1f2b', paddingTop: 6 }}>
                📊 Token：输入 {msg.promptTokens || 0} · 输出 {msg.completionTokens || 0}
              </div>
            ) : null}
          </div>
        ))}
        {loading && (
          <div style={{ ...styles.chatBubble, alignSelf: 'flex-start', background: '#1f2530', borderColor: '#252b36' }}>
            <span className="typing-dot" />
            <span className="typing-dot" />
            <span className="typing-dot" />
          </div>
        )}
        <div ref={chatEndRef} />
      </div>

      {/* 输入区 */}
      <div style={styles.chatInputArea}>
        <textarea
          style={styles.chatInput}
          placeholder="输入用户消息…"
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          rows={2}
        />
        <button
          style={{ ...styles.chatSendBtn, opacity: !isLLM || loading ? 0.4 : 1 }}
          onClick={handleSend}
          disabled={!isLLM || loading}
        >
          {loading ? '…' : '发送'}
        </button>
      </div>
    </div>
  );
}

const styles = {
  chatContainer: { display: 'flex', flexDirection: 'column', height: '100%' },
  chatHeader: {
    padding: '10px 14px',
    fontWeight: 600,
    fontSize: 13,
    color: '#c9cdd4',
    borderBottom: '1px solid #1a1f2b',
  },
  chatMessages: {
    flex: 1,
    overflowY: 'auto',
    padding: 12,
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
  },
  chatEmpty: { color: '#5a606b', textAlign: 'center', padding: 24, fontSize: 12 },
  chatBubble: {
    maxWidth: '92%',
    padding: '10px 12px',
    borderRadius: 8,
    border: '1px solid #252b36',
    wordBreak: 'break-word',
    fontSize: 12,
    lineHeight: 1.6,
  },
  chatRole: {
    fontSize: 10,
    fontWeight: 700,
    marginBottom: 4,
    opacity: 0.6,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  chatInputArea: {
    padding: '10px 12px',
    borderTop: '1px solid #1a1f2b',
    display: 'flex',
    gap: 8,
  },
  chatInput: {
    flex: 1,
    padding: '8px 10px',
    background: '#151a24',
    border: '1px solid #222833',
    borderRadius: 8,
    color: '#c9cdd4',
    fontSize: 12,
    resize: 'none',
    outline: 'none',
    fontFamily: 'inherit',
  },
  chatSendBtn: {
    padding: '8px 16px',
    background: '#5e9cf5',
    color: '#fff',
    border: 'none',
    borderRadius: 8,
    cursor: 'pointer',
    fontWeight: 600,
    fontSize: 12,
    alignSelf: 'flex-end',
  },
};
