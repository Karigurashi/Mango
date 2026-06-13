import { useState, useEffect, useCallback, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';
import { flowToJson } from '../utils/workflowIO';
import { EExecutionStatus } from './Canvas';
import { API_BASE } from './ChatPanel';

/**
 * 运行面板 — 将画布工作流发送至后端执行，日志+流式输出。
 */
export default function RunPanel({ nodes, edges, name, variables, setNodeStatuses }) {
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

        {/* 流式块 */}
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

// ==================== StreamBlock ====================

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
