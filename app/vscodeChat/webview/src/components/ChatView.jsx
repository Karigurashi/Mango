import React, { useEffect, useRef } from 'react';
import useChatStore from '../hooks/useChatStore';
import useWebSocket from '../hooks/useWebSocket';
import MessageList from './MessageList';
import InputBar from './InputBar';
import TokenFooter from './TokenFooter';

const wsUrl = window.__WS_URL__ || 'ws://127.0.0.1:0';
const vscodeApi = window.__VSCODE_API__;

export default function ChatView() {
  const store = useChatStore();
  const { send } = useWebSocket(wsUrl, store);

  // 监听来自 Extension 的 postMessage（VSCode API 通道）
  useEffect(() => {
    const handler = (event) => {
      const msg = event.data;
      if (!msg || !msg.type) return;
      switch (msg.type) {
        case 'models':
          // 模型列表由扩展推送
          break;
        case 'workspaceInfo':
          break;
        case 'focusInput':
          document.querySelector('.chat-input-textarea')?.focus();
          break;
        case 'backendStatus':
          store.backendStatus?.(msg.status);
          break;
      }
    };
    window.addEventListener('message', handler);
    return () => window.removeEventListener('message', handler);
  }, [store]);

  const handleSend = (text) => {
    store.addUserMsg(text);
    send({ type: 'chat', message: text, model: '' });
  };

  const handleCancel = () => {
    send({ type: 'cancel' });
  };

  const handleSwitchModel = (model) => {
    send({ type: 'switchModel', model });
    store.modelSwitched(model);
  };

  const handleClear = () => {
    send({ type: 'clear' });
    store.cleared();
  };

  return (
    <div style={styles.root}>
      {/* Header */}
      <div style={styles.header}>
        <span style={styles.headerTitle}>Qoder Chat</span>
        {store.backendStatus !== 'connected' && (
          <span style={styles.statusBadge(store.backendStatus)}>
            {store.backendStatus === 'disconnected' ? 'Reconnecting...' : 'Offline'}
          </span>
        )}
        {store.modelName && (
          <span style={styles.modelBadge}>{store.modelName}</span>
        )}
        <button style={styles.clearBtn} onClick={handleClear} title="Clear context">
          Clear
        </button>
      </div>

      {/* Messages */}
      <MessageList
        messages={store.messages}
        streamingMsg={store.streamingMsg}
        status={store.status}
      />

      {/* Token Footer */}
      {store.streamingMsg && (
        <TokenFooter msg={store.streamingMsg} />
      )}

      {/* Input */}
      <InputBar
        status={store.status}
        modelName={store.modelName}
        onSend={handleSend}
        onCancel={handleCancel}
        onSwitchModel={handleSwitchModel}
      />
    </div>
  );
}

const styles = {
  root: {
    display: 'flex',
    flexDirection: 'column',
    height: '100vh',
    background: 'var(--bg-root, #0d1117)',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    padding: '8px 14px',
    borderBottom: '1px solid var(--border, #222833)',
    background: 'var(--bg-panel, #161b22)',
    flexShrink: 0,
  },
  headerTitle: {
    fontWeight: 700,
    fontSize: 13,
    color: 'var(--text-primary, #c9cdd4)',
  },
  statusBadge: (status) => ({
    fontSize: 10,
    padding: '2px 8px',
    borderRadius: 10,
    background: status === 'disconnected' ? 'rgba(230,180,80,0.15)' : 'rgba(242,85,90,0.15)',
    color: status === 'disconnected' ? '#e6b450' : '#f2555a',
  }),
  modelBadge: {
    fontSize: 10,
    padding: '2px 8px',
    borderRadius: 10,
    background: 'rgba(94,156,245,0.12)',
    color: '#58a6ff',
    marginLeft: 'auto',
  },
  clearBtn: {
    fontSize: 11,
    padding: '3px 10px',
    background: 'transparent',
    border: '1px solid var(--border, #222833)',
    borderRadius: 4,
    color: 'var(--text-muted, #5a606b)',
    cursor: 'pointer',
  },
};
