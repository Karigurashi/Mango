import { useState } from 'react';
import ModelDropdown from './ModelDropdown';

export default function InputBar({ status, modelName, onSend, onCancel, onSwitchModel }) {
  const [text, setText] = useState('');
  const isRunning = status === 'streaming';

  const handleSend = () => {
    const trimmed = text.trim();
    if (!trimmed || isRunning) return;
    onSend(trimmed);
    setText('');
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div style={styles.wrapper}>
      {/* Model selector row */}
      <div style={styles.topRow}>
        <ModelDropdown
          currentModel={modelName}
          onSelect={onSwitchModel}
          disabled={isRunning}
        />
      </div>

      {/* Input row */}
      <div style={styles.inputRow}>
        <textarea
          className="chat-input-textarea"
          style={styles.textarea}
          placeholder={isRunning ? 'Agent is running...' : 'Ask anything... (Enter to send, Shift+Enter for newline)'}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={2}
          disabled={isRunning}
        />
        <button
          style={isRunning ? styles.stopBtn : styles.sendBtn(!text.trim())}
          onClick={isRunning ? onCancel : handleSend}
          title={isRunning ? 'Stop' : 'Send'}
        >
          {isRunning ? '\u25A0' : '\u2191'}
        </button>
      </div>
    </div>
  );
}

const styles = {
  wrapper: {
    borderTop: '1px solid var(--border, #222833)',
    padding: '8px 10px 10px',
    background: 'var(--bg-root, #0d1117)',
    flexShrink: 0,
  },
  topRow: {
    display: 'flex',
    alignItems: 'center',
    marginBottom: 6,
  },
  inputRow: {
    display: 'flex',
    gap: 7,
    alignItems: 'flex-end',
  },
  textarea: {
    flex: 1,
    padding: '7px 10px',
    background: 'var(--bg-input, #151a24)',
    border: '1px solid var(--border, #222833)',
    borderRadius: 8,
    color: 'var(--text-primary, #c9cdd4)',
    fontSize: 12.5,
    lineHeight: 1.5,
    resize: 'none',
    outline: 'none',
    fontFamily: 'inherit',
  },
  sendBtn: (disabled) => ({
    width: 34,
    height: 34,
    borderRadius: 8,
    background: disabled ? 'var(--border, #222833)' : '#58a6ff',
    color: '#fff',
    border: 'none',
    cursor: disabled ? 'not-allowed' : 'pointer',
    fontSize: 18,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
    opacity: disabled ? 0.5 : 1,
    transition: 'background 0.15s',
  }),
  stopBtn: {
    width: 34,
    height: 34,
    borderRadius: 8,
    background: '#f2555a',
    color: '#fff',
    border: 'none',
    cursor: 'pointer',
    fontSize: 16,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
};
