import { useState, useRef, useEffect } from 'react';

const AVAILABLE_MODELS = [
  { key: 'deepseek-high', label: 'DeepSeek V3 (High)', short: 'DS-H' },
  { key: 'deepseek-chat', label: 'DeepSeek V3', short: 'DS' },
  { key: 'gemini-flash', label: 'Gemini Flash', short: 'GM-F' },
  { key: 'claude-sonnet', label: 'Claude Sonnet', short: 'CL-S' },
];

export default function ModelDropdown({ currentModel, onSelect, disabled }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  // 点击外部关闭
  useEffect(() => {
    if (!open) return;
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  const current = AVAILABLE_MODELS.find((m) => m.key === currentModel) || AVAILABLE_MODELS[0];

  return (
    <div ref={ref} style={styles.container}>
      <button
        style={styles.trigger(disabled)}
        onClick={() => !disabled && setOpen(!open)}
        disabled={disabled}
      >
        <span style={styles.dot} />
        <span style={styles.label}>{current.short || currentModel || 'Model'}</span>
        <span style={styles.arrow(open)}>&#x25BC;</span>
      </button>

      {open && (
        <div style={styles.dropdown}>
          {AVAILABLE_MODELS.map((m) => (
            <button
              key={m.key}
              style={styles.item(m.key === (currentModel || 'deepseek-high'))}
              onClick={() => {
                onSelect(m.key);
                setOpen(false);
              }}
            >
              <span style={styles.itemDot(m.key === (currentModel || 'deepseek-high'))} />
              <div>
                <div style={styles.itemLabel}>{m.label}</div>
                <div style={styles.itemKey}>{m.key}</div>
              </div>
              {m.key === (currentModel || 'deepseek-high') && (
                <span style={styles.check}>&#x2713;</span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

const styles = {
  container: {
    position: 'relative',
  },
  trigger: (disabled) => ({
    display: 'flex',
    alignItems: 'center',
    gap: 5,
    padding: '4px 10px',
    background: 'var(--bg-input, #151a24)',
    border: '1px solid var(--border, #222833)',
    borderRadius: 6,
    color: 'var(--text-secondary, #8b919b)',
    fontSize: 11,
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.5 : 1,
  }),
  dot: {
    width: 6,
    height: 6,
    borderRadius: '50%',
    background: '#58a6ff',
    flexShrink: 0,
  },
  label: {
    fontWeight: 600,
    color: '#58a6ff',
  },
  arrow: (open) => ({
    fontSize: 8,
    transition: 'transform 0.15s',
    transform: open ? 'rotate(180deg)' : 'none',
  }),
  dropdown: {
    position: 'absolute',
    bottom: '100%',
    left: 0,
    marginBottom: 4,
    minWidth: 200,
    background: 'var(--bg-elevated, #1f2530)',
    border: '1px solid var(--border, #222833)',
    borderRadius: 8,
    boxShadow: '0 8px 24px rgba(0,0,0,0.6)',
    zIndex: 100,
    padding: 4,
    display: 'flex',
    flexDirection: 'column',
    gap: 2,
  },
  item: (active) => ({
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    padding: '6px 10px',
    borderRadius: 6,
    border: 'none',
    background: active ? 'rgba(94,156,245,0.08)' : 'transparent',
    color: 'var(--text-primary, #c9cdd4)',
    fontSize: 12,
    cursor: 'pointer',
    textAlign: 'left',
    width: '100%',
    transition: 'background 0.1s',
  }),
  itemDot: (active) => ({
    width: 7,
    height: 7,
    borderRadius: '50%',
    background: active ? '#58a6ff' : '#5a606b',
    flexShrink: 0,
  }),
  itemLabel: {
    fontWeight: 500,
    lineHeight: 1.3,
  },
  itemKey: {
    fontSize: 10,
    color: 'var(--text-muted, #5a606b)',
  },
  check: {
    marginLeft: 'auto',
    color: '#58a6ff',
    fontSize: 13,
    fontWeight: 700,
  },
};
