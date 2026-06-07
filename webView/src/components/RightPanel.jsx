import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';
import { getNodeDef, CATEGORY_LABEL_COLORS, CONFIG_TYPE_COLORS } from '../nodes/nodeRegistry';
import { flowToJson } from '../utils/workflowIO';
import { EExecutionStatus } from './Canvas';

/**
 * 右侧面板 — 属性 / 对话 / 运行 三 Tab，支持拖拽宽度、收起、Markdown 渲染。
 */
export default function RightPanel({
  selectedNode, nodes, setNodes, edges, name, variables,
  panelWidth, collapsed, onToggleCollapse, setNodeStatuses,
}) {
  const [activeTab, setActiveTab] = useState('properties');

  const tabs = [
    { key: 'properties', label: '属性' },
    { key: 'chat', label: '对话' },
    { key: 'run', label: '运行' },
  ];

  if (collapsed) {
    return (
      <div style={styles.collapsedBar} onClick={onToggleCollapse} title="展开属性面板">
        <span style={styles.collapsedText}>属性</span>
        <span style={styles.collapsedIcon}>◀</span>
      </div>
    );
  }

  return (
    <div style={{ ...styles.container, width: panelWidth, minWidth: panelWidth }}>
      {/* Tab 栏 */}
      <div style={styles.tabBar}>
        {tabs.map((t) => (
          <button
            key={t.key}
            style={{ ...styles.tab, ...(activeTab === t.key ? styles.tabActive : {}) }}
            onClick={() => setActiveTab(t.key)}
          >
            {t.label}
          </button>
        ))}
        <button style={styles.collapseBtn} onClick={onToggleCollapse} title="收起面板">
          ▶
        </button>
      </div>

      {/* Tab 内容 */}
      <div style={styles.tabContent}>
        {activeTab === 'properties' && (
          <PropertiesTab selectedNode={selectedNode} nodes={nodes} setNodes={setNodes} />
        )}
        {activeTab === 'chat' && (
          <ChatTab selectedNode={selectedNode} nodes={nodes} setNodes={setNodes} />
        )}
        {activeTab === 'run' && (
          <RunTab nodes={nodes} edges={edges} name={name} variables={variables} setNodeStatuses={setNodeStatuses} />
        )}
      </div>
    </div>
  );
}

// ==================== 属性 Tab ====================

function PropertiesTab({ selectedNode, nodes, setNodes }) {
  const [localConfig, setLocalConfig] = useState({});
  const [localName, setLocalName] = useState('');
  const prevNodeRef = useRef(null);

  // 用 selectedNode 对象引用作为 key，确保节点切换时强制刷新
  useEffect(() => {
    if (selectedNode && selectedNode !== prevNodeRef.current) {
      prevNodeRef.current = selectedNode;
      setLocalConfig({ ...(selectedNode.data.config || {}) });
      setLocalName(selectedNode.data.name || '');
    } else if (!selectedNode) {
      prevNodeRef.current = null;
      setLocalConfig({});
      setLocalName('');
    }
  }, [selectedNode]);

  const nodeDef = useMemo(
    () => (selectedNode ? getNodeDef(selectedNode.data.nodeType) : null),
    [selectedNode?.data?.nodeType]
  );

  if (!selectedNode) {
    return <div style={styles.empty}>选中一个节点以编辑参数</div>;
  }

  if (!nodeDef) {
    return <div style={styles.empty}>未知节点类型</div>;
  }

  const configFields = nodeDef.configSchema || [];
  const labelColor = CATEGORY_LABEL_COLORS[nodeDef.category] || '#5e9cf5';

  const handleNameChange = (value) => {
    setLocalName(value);
    setNodes((nds) =>
      nds.map((n) =>
        n.id === selectedNode.id
          ? { ...n, data: { ...n.data, name: value || null } }
          : n
      )
    );
  };

  const handleChange = (fieldName, value) => {
    const newConfig = { ...localConfig, [fieldName]: value };
    setLocalConfig(newConfig);
    setNodes((nds) =>
      nds.map((n) =>
        n.id === selectedNode.id
          ? { ...n, data: { ...n.data, config: newConfig } }
          : n
      )
    );
  };

  const renderInput = (field) => {
    const value = localConfig[field.name] ?? field.default ?? '';
    const s = { ...styles.propInput };

    switch (field.type) {
      case 'bool':
        return (
          <select style={s} value={value === true || value === 'true' ? 'true' : 'false'}
            onChange={(e) => handleChange(field.name, e.target.value === 'true')}>
            <option value="true">True</option>
            <option value="false">False</option>
          </select>
        );
      case 'int':
        return (
          <input type="number" step="1" style={s} value={value}
            onChange={(e) => handleChange(field.name, e.target.value === '' ? '' : parseInt(e.target.value, 10))} />
        );
      case 'float':
        return (
          <input type="number" step="0.1" style={s} value={value}
            onChange={(e) => handleChange(field.name, e.target.value === '' ? '' : parseFloat(e.target.value))} />
        );
      default:
        return (
          <input type="text" style={s} value={value}
            onChange={(e) => handleChange(field.name, e.target.value)} />
        );
    }
  };

  return (
    <div>
      {/* 节点信息 */}
      <div style={styles.section}>
        <div style={styles.sectionTitle}>
          <span style={{ ...styles.categoryBadge, background: labelColor + '22', color: labelColor, border: `1px solid ${labelColor}44` }}>
            {nodeDef.category}
          </span>
          {nodeDef.displayName}
        </div>
        <div style={styles.infoRow}>
          <span style={styles.infoLabel}>ID</span>
          <code style={styles.mono}>{selectedNode.id}</code>
        </div>
        <div style={styles.infoRow}>
          <span style={styles.infoLabel}>类型</span>
          <code style={styles.mono}>{selectedNode.data.nodeType}</code>
        </div>
        <div style={styles.desc}>{nodeDef.description}</div>
      </div>

      {/* 节点名称 */}
      <div style={styles.section}>
        <div style={styles.sectionLabel}>节点名称</div>
        <input
          type="text"
          style={styles.propInput}
          placeholder={nodeDef.displayName}
          value={localName}
          onChange={(e) => handleNameChange(e.target.value)}
        />
        <div style={{ fontSize: 10, color: '#5a606b', marginTop: 4 }}>
          留空则使用默认名称「{nodeDef.displayName}」
        </div>
      </div>

      {/* 可配置参数 */}
      {configFields.length > 0 && (
        <div style={styles.section}>
          <div style={styles.sectionLabel}>配置参数</div>
          {configFields.map((f) => (
            <div key={f.name} style={styles.editRow}>
              <label style={styles.editLabel} title={f.description}>
                {f.name}
                <span style={styles.editType}>{f.type}</span>
              </label>
              {renderInput(f)}
            </div>
          ))}
        </div>
      )}

      {configFields.length === 0 && (
        <div style={styles.section}>
          <div style={styles.emptySm}>此节点无可配置参数</div>
        </div>
      )}
    </div>
  );
}

// ==================== 对话 Tab ====================

const API_BASE = 'http://127.0.0.1:8765';

function ChatTab({ selectedNode, nodes, setNodes }) {
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
    const assistantMsgIndex = messages.length + 1;
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

// ==================== 运行 Tab ====================

function RunTab({ nodes, edges, name, variables, setNodeStatuses }) {
  const [logEntries, setLogEntries] = useState([]);
  const [streamBlocks, setStreamBlocks] = useState({});
  const [isRunning, setIsRunning] = useState(false);
  const logEndRef = useRef(null);
  const abortRef = useRef(null);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logEntries, streamBlocks]);

  useEffect(() => {
    return () => {
      if (abortRef.current) abortRef.current.abort();
      if (setNodeStatuses) setNodeStatuses({});
    };
  }, [setNodeStatuses]);

  const runSimulation = useCallback(async () => {
    const entryNodes = nodes.filter(
      (n) => n.data?.nodeType === 'Action/BeginPlay'
    );
    if (entryNodes.length === 0) {
      setLogEntries([{ id: Date.now(), type: 'error', msg: '未找到 BeginPlay 入口节点！请从节点面板拖入 动作 > Begin Play。', time: Date.now() }]);
      return;
    }

    setIsRunning(true);
    setLogEntries([]);
    setStreamBlocks({});
    if (setNodeStatuses) setNodeStatuses({});

    const addLog = (level, msg) => {
      setLogEntries((prev) => [...prev, { id: Date.now() + Math.random(), type: 'log', level, msg, time: Date.now() }]);
    };

    const wfJson = flowToJson(nodes, edges, name, variables);
    addLog('info', `工作流「${name || '未命名'}」发送至后端 — ${nodes.length} 个节点, ${edges.length} 条连线`);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const res = await fetch(`${API_BASE}/api/run/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(wfJson),
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

            if (event.type === 'node') {
              if (setNodeStatuses) {
                setNodeStatuses((prev) => ({ ...prev, [event.nodeId]: event.status }));
              }
              const statusEmoji = event.status === EExecutionStatus.RUNNING ? '▶' : event.status === EExecutionStatus.COMPLETED ? '✅' : event.status === EExecutionStatus.FAILED ? '❌' : '⏹';
              addLog('action', `${statusEmoji} [节点${event.nodeId}] ${event.status}`);
            } else if (event.type === 'log') {
              addLog(event.level, event.msg);
            } else if (event.type === 'stream') {
              // 流式事件：按 context.ExecutionRound 分组
              const nid = event.nodeId;
              const round = Number(event.data?.round || 1);
              const blockKey = `${nid}#${round}`;
              setStreamBlocks((prev) => {
                const old = prev[blockKey] || {
                  nodeId: nid,
                  round,
                  thinking: '',
                  content: '',
                  promptTokens: 0,
                  completionTokens: 0,
                  completed: false,
                  thinkingCollapsed: false,
                };
                const updated = { ...old };
                if (event.eventType === 'thinking') {
                  updated.thinking = old.thinking + (event.data?.text || '');
                } else if (event.eventType === 'content') {
                  updated.content = old.content + (event.data?.text || '');
                } else if (event.eventType === 'usage') {
                  updated.promptTokens = event.data?.promptTokens || 0;
                  updated.completionTokens = event.data?.completionTokens || 0;
                } else if (event.eventType === 'done') {
                  updated.completed = true;
                }
                return { ...prev, [blockKey]: updated };
              });
            } else if (event.type === 'done') {
              addLog('info', '✅ 工作流执行完成');
              if (event.blackboard && Object.keys(event.blackboard).length > 0) {
                addLog('info', `执行结果：\n${JSON.stringify(event.blackboard, null, 2)}`);
              }
              if (setNodeStatuses) setNodeStatuses({});
            } else if (event.type === 'cancelled') {
              addLog('info', '⏹ 工作流已被中断');
              if (setNodeStatuses) setNodeStatuses({});
            } else if (event.type === 'error') {
              addLog('error', `执行失败：${event.msg}`);
              if (setNodeStatuses) setNodeStatuses({});
            }
          } catch (parseErr) {
            // 忽略解析错误
          }
        }
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        addLog('error', `❌ 请求失败：${err.message}`);
      } else {
        addLog('info', '⏹ 已中断执行');
      }
    } finally {
      setIsRunning(false);
      abortRef.current = null;
      if (setNodeStatuses) setNodeStatuses({});
    }
  }, [nodes, edges, name, variables, setNodeStatuses]);

  const handleInterrupt = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
    }
  }, []);

  const toggleThinking = useCallback((blockKey) => {
    setStreamBlocks((prev) => {
      const block = prev[blockKey];
      if (!block) return prev;
      return { ...prev, [blockKey]: { ...block, thinkingCollapsed: !block.thinkingCollapsed } };
    });
  }, []);

  const logColor = (level) => {
    switch (level) {
      case 'error': return '#f2555a';
      case 'llm': return '#5e9cf5';
      case 'response': return '#3ecf8e';
      case 'action': return '#e6b450';
      case 'info': return '#8b919b';
      default: return '#5a606b';
    }
  };

  const hasContent = logEntries.length > 0 || Object.keys(streamBlocks).length > 0;

  return (
    <div style={styles.runContainer}>
      <div style={styles.runHeader}>
        <span>工作流运行器</span>
        {isRunning ? (
          <button style={styles.runStopBtn} onClick={handleInterrupt}>■ 中断</button>
        ) : (
          <button style={styles.runBtn} onClick={runSimulation}>▶ 运行模拟</button>
        )}
      </div>

      <div style={styles.runLog}>
        {!hasContent && (
          <div style={styles.runEmpty}>
            点击「运行模拟」执行工作流
            <br /><br />
            <small>将当前画布中的节点和连线发送至后端执行。</small>
            <br />
            <small>LLM 节点会真实调用大模型，并流式展示生成内容。</small>
          </div>
        )}

        {/* 日志条目 */}
        {logEntries.map((entry) => (
          <div key={entry.id} style={{ ...styles.logEntry, color: logColor(entry.level) }}>
            <span style={styles.logTime}>{new Date(entry.time).toLocaleTimeString()}</span>
            {entry.msg}
          </div>
        ))}

        {/* 流式块：每个 LLM 节点每轮一个块 */}
        {Object.entries(streamBlocks).map(([blockKey, block]) => (
          <StreamBlock
            key={blockKey}
            nodeId={block.nodeId}
            round={block.round}
            block={block}
            onToggleThinking={() => toggleThinking(blockKey)}
          />
        ))}

        <div ref={logEndRef} />
      </div>
    </div>
  );
}

/** LLM 节点流式输出块 */
function StreamBlock({ nodeId, round, block, onToggleThinking }) {
  const { thinking, content, promptTokens, completionTokens, completed, thinkingCollapsed } = block;

  return (
    <div style={styles.streamBlock}>
      <div style={styles.streamHeader}>
        <span style={{ color: '#5e9cf5', fontWeight: 600 }}>
          🤖 节点 [{nodeId}] LLM 输出 · 第 {round} 轮
        </span>
        {completed ? (
          <span style={{ fontSize: 10, color: '#3ecf8e' }}>✅ 完成</span>
        ) : (
          <span style={{ fontSize: 10, color: '#e6b450' }}>⏳ 生成中…</span>
        )}
      </div>

      {/* 思考过程（可折叠） */}
      {thinking && (
        <div style={styles.thinkingSection}>
          <div
            style={styles.thinkingToggle}
            onClick={onToggleThinking}
          >
            <span style={{ fontSize: 10, marginRight: 4 }}>{thinkingCollapsed ? '▶' : '▼'}</span>
            💭 思考过程
          </div>
          {!thinkingCollapsed && (
            <div className="md-content" style={styles.thinkingContent}>
              <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>
                {thinking}
              </ReactMarkdown>
            </div>
          )}
        </div>
      )}

      {/* 正文内容 */}
      {content && (
        <div className="md-content" style={styles.streamContent}>
          <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>
            {content}
          </ReactMarkdown>
        </div>
      )}

      {/* 无内容时显示等待 */}
      {!thinking && !content && !completed && (
        <div style={{ color: '#5a606b', fontSize: 11, fontStyle: 'italic', padding: '4px 0' }}>
          等待模型响应…
        </div>
      )}

      {/* Token 用量 */}
      {(promptTokens > 0 || completionTokens > 0) && (
        <div style={styles.streamTokens}>
          📊 Token：输入 {promptTokens} · 输出 {completionTokens}
        </div>
      )}
    </div>
  );
}

// ==================== Styles ====================

const styles = {
  container: {
    height: '100%',
    background: '#12161e',
    borderLeft: '1px solid #222833',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    fontSize: 13,
    color: '#c9cdd4',
  },
  collapsedBar: {
    width: 30,
    minWidth: 30,
    height: '100%',
    background: '#12161e',
    borderLeft: '1px solid #222833',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    cursor: 'pointer',
    color: '#5a606b',
    writingMode: 'vertical-rl',
    fontSize: 11,
    fontWeight: 600,
    letterSpacing: 2,
  },
  collapsedText: { marginBottom: 4 },
  collapsedIcon: { fontSize: 10 },
  tabBar: {
    display: 'flex',
    borderBottom: '1px solid #222833',
    background: '#191e28',
  },
  collapseBtn: {
    background: 'transparent',
    color: '#5a606b',
    fontSize: 11,
    padding: '0 10px',
    marginLeft: 'auto',
  },
  tab: {
    flex: 1,
    padding: '9px 6px',
    background: 'transparent',
    color: '#8b919b',
    border: 'none',
    cursor: 'pointer',
    fontSize: 12,
    fontWeight: 600,
    borderBottom: '2px solid transparent',
    transition: 'all 0.15s',
  },
  tabActive: {
    color: '#c9cdd4',
    borderBottomColor: '#5e9cf5',
  },
  tabContent: {
    flex: 1,
    overflowY: 'auto',
  },
  empty: {
    padding: 24,
    color: '#5a606b',
    textAlign: 'center',
    fontSize: 13,
  },
  emptySm: {
    color: '#5a606b',
    textAlign: 'center',
    fontSize: 12,
    padding: '8px 0',
  },

  // 属性
  section: {
    padding: '12px 14px',
    borderBottom: '1px solid #1a1f2b',
  },
  sectionTitle: {
    fontSize: 14,
    fontWeight: 700,
    color: '#c9cdd4',
    marginBottom: 8,
    display: 'flex',
    alignItems: 'center',
    gap: 8,
  },
  sectionLabel: {
    fontSize: 11,
    fontWeight: 700,
    textTransform: 'uppercase',
    color: '#8b919b',
    marginBottom: 8,
    letterSpacing: 0.5,
  },
  categoryBadge: {
    display: 'inline-block',
    padding: '2px 7px',
    borderRadius: 4,
    fontSize: 10,
    fontWeight: 700,
    textTransform: 'uppercase',
  },
  infoRow: {
    display: 'flex',
    justifyContent: 'space-between',
    marginBottom: 3,
  },
  infoLabel: { color: '#8b919b', fontSize: 11 },
  mono: {
    fontFamily: "'JetBrains Mono', 'Consolas', monospace",
    fontSize: 11,
    color: '#8b919b',
  },
  desc: {
    fontSize: 11,
    color: '#5a606b',
    marginTop: 6,
    fontStyle: 'italic',
  },
  editRow: { marginBottom: 8 },
  editLabel: {
    fontSize: 11,
    color: '#8b919b',
    marginBottom: 3,
    display: 'flex',
    alignItems: 'center',
    gap: 6,
  },
  editType: {
    fontSize: 9,
    color: '#5a606b',
    fontFamily: "'JetBrains Mono', monospace",
    textTransform: 'uppercase',
  },
  propInput: {
    width: '100%',
    padding: '6px 8px',
    background: '#151a24',
    border: '1px solid #222833',
    borderRadius: 6,
    fontSize: 12,
    fontFamily: "'JetBrains Mono', 'Consolas', monospace",
    outline: 'none',
    color: '#c9cdd4',
    transition: 'border-color 0.15s',
    boxSizing: 'border-box',
  },

  // 对话
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

  // 运行
  runContainer: { display: 'flex', flexDirection: 'column', height: '100%' },
  runHeader: {
    padding: '10px 14px',
    borderBottom: '1px solid #1a1f2b',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    fontWeight: 600,
    fontSize: 13,
  },
  runBtn: {
    padding: '6px 14px',
    background: '#1a332a',
    color: '#3ecf8e',
    border: '1px solid #234d38',
    borderRadius: 6,
    cursor: 'pointer',
    fontWeight: 600,
    fontSize: 11,
  },
  runStopBtn: {
    padding: '6px 14px',
    background: '#2e1a1c',
    color: '#f2555a',
    border: '1px solid #f2555a44',
    borderRadius: 6,
    cursor: 'pointer',
    fontWeight: 600,
    fontSize: 11,
  },
  runLog: {
    flex: 1,
    overflowY: 'auto',
    padding: 12,
    fontFamily: "'JetBrains Mono', 'Consolas', monospace",
    fontSize: 11,
    lineHeight: 1.7,
  },
  runEmpty: { color: '#5a606b', textAlign: 'center', padding: 24 },
  logEntry: {
    padding: '3px 0',
    borderBottom: '1px solid #151a24',
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-word',
  },
  logTime: { color: '#3d4550', marginRight: 10, fontSize: 10 },

  // 流式块
  streamBlock: {
    margin: '8px 0',
    padding: 10,
    background: '#151a24',
    border: '1px solid #222833',
    borderRadius: 8,
    fontFamily: 'inherit',
  },
  streamHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
    paddingBottom: 6,
    borderBottom: '1px solid #1a1f2b',
    fontSize: 12,
  },
  streamContent: {
    fontSize: 12,
    lineHeight: 1.7,
    color: '#c9cdd4',
    wordBreak: 'break-word',
  },
  streamTokens: {
    marginTop: 8,
    paddingTop: 6,
    borderTop: '1px solid #1a1f2b',
    fontSize: 10,
    color: '#5a606b',
  },

  // 思考过程
  thinkingSection: {
    marginBottom: 8,
  },
  thinkingToggle: {
    cursor: 'pointer',
    color: '#e6b450',
    fontWeight: 600,
    fontSize: 11,
    userSelect: 'none',
    padding: '4px 0',
  },
  thinkingContent: {
    marginTop: 4,
    padding: '8px 10px',
    background: '#0d1117',
    borderRadius: 6,
    border: '1px solid #2b2418',
    fontSize: 11,
    lineHeight: 1.6,
    color: '#8b919b',
    maxHeight: 240,
    overflowY: 'auto',
  },
};
