import { useState } from 'react';

export default function ToolCallCard({ tool }) {
  const [open, setOpen] = useState(false);
  const isDone = tool.status === 'done';
  const isError = tool.success === false;

  const statusColor = isDone
    ? (isError ? '#f2555a' : '#3fb950')
    : '#e6b450';

  return (
    <details open={open} onToggle={(e) => setOpen(e.target.open)} style={styles.details}>
      <summary style={styles.summary}>
        <span style={{ ...styles.dot, background: statusColor }} />
        <span style={styles.toolName}>{tool.name}</span>
        {isDone && (
          <span style={{ ...styles.status, color: isError ? '#f2555a' : '#3fb950' }}>
            {isError ? 'Failed' : 'Done'}
          </span>
        )}
      </summary>
      <div style={styles.body}>
        {/* Args */}
        {tool.args && Object.keys(tool.args).length > 0 && (
          <div style={styles.section}>
            <div style={styles.sectionLabel}>Arguments</div>
            <pre style={styles.pre}>{JSON.stringify(tool.args, null, 2)}</pre>
          </div>
        )}
        {/* Result */}
        {tool.result && (
          <div style={styles.section}>
            <div style={styles.sectionLabel}>Result</div>
            <pre style={{ ...styles.pre, borderColor: isError ? '#f2555a44' : '#3fb95044' }}>
              {typeof tool.result === 'string' ? tool.result : JSON.stringify(tool.result, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </details>
  );
}

const styles = {
  details: {
    marginBottom: 0,
  },
  summary: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    cursor: 'pointer',
    userSelect: 'none',
    padding: '3px 0',
  },
  dot: {
    width: 6,
    height: 6,
    borderRadius: '50%',
    flexShrink: 0,
  },
  toolName: {
    fontSize: 11,
    fontWeight: 600,
    color: '#3fb950',
  },
  status: {
    fontSize: 10,
    marginLeft: 'auto',
    opacity: 0.8,
  },
  body: {
    marginTop: 4,
    padding: '6px 8px',
    background: 'rgba(0,0,0,0.2)',
    borderRadius: 6,
    fontSize: 10.5,
    lineHeight: 1.5,
    color: '#8b919b',
    maxHeight: 200,
    overflowY: 'auto',
  },
  section: {
    marginBottom: 6,
  },
  sectionLabel: {
    fontSize: 10,
    fontWeight: 600,
    color: '#5a606b',
    marginBottom: 2,
  },
  pre: {
    margin: 0,
    padding: '4px 6px',
    background: 'rgba(0,0,0,0.2)',
    borderRadius: 4,
    border: '1px solid #222833',
    fontFamily: "'JetBrains Mono', 'Consolas', monospace",
    fontSize: 10,
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-word',
    overflow: 'hidden',
  },
};
