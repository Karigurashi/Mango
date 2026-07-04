import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export default function ThinkingBlock({ content }) {
  const [open, setOpen] = useState(true);

  if (!content) return null;

  return (
    <details open={open} style={styles.details} onToggle={(e) => setOpen(e.target.open)}>
      <summary style={styles.summary}>
        <span style={styles.icon}>&#x25C6;</span>
        Thinking
      </summary>
      <div className="thinking-content" style={styles.body}>
        <ReactMarkdown remarkPlugins={[remarkGfm]}>
          {content}
        </ReactMarkdown>
      </div>
    </details>
  );
}

const styles = {
  details: {
    marginBottom: 8,
  },
  summary: {
    cursor: 'pointer',
    color: '#d29922',
    fontWeight: 600,
    fontSize: 11,
    userSelect: 'none',
    padding: '2px 0',
  },
  icon: {
    marginRight: 4,
    fontSize: 10,
  },
  body: {
    marginTop: 4,
    padding: '8px 10px',
    background: 'rgba(210,153,34,0.06)',
    borderRadius: 6,
    border: '1px solid rgba(210,153,34,0.15)',
    fontSize: 11,
    lineHeight: 1.6,
    color: '#8b919b',
    maxHeight: 240,
    overflowY: 'auto',
  },
};
