import { useEffect, useRef } from 'react';
import MessageBubble from './MessageBubble';

export default function MessageList({ messages, streamingMsg, status }) {
  const bottomRef = useRef(null);
  const containerRef = useRef(null);
  const userScrolledUpRef = useRef(false);

  // 自动滚底（用户手动上滚时暂停）
  useEffect(() => {
    if (userScrolledUpRef.current) return;
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingMsg]);

  const handleScroll = () => {
    const el = containerRef.current;
    if (!el) return;
    const dist = el.scrollHeight - el.scrollTop - el.clientHeight;
    userScrolledUpRef.current = dist > 50;
  };

  const allMessages = streamingMsg
    ? [...messages, { ...streamingMsg, _streaming: true }]
    : messages;

  return (
    <div style={styles.container} ref={containerRef} onScroll={handleScroll}>
      {allMessages.length === 0 && status === 'idle' && (
        <div style={styles.empty}>
          <div style={styles.emptyIcon}>Q</div>
          <div style={styles.emptyTitle}>Qoder Chat</div>
          <div style={styles.emptySub}>Ask anything about your codebase</div>
        </div>
      )}
      {allMessages.map((msg, i) => (
        <MessageBubble key={msg.id || i} msg={msg} />
      ))}
      {status === 'streaming' && !streamingMsg?.content && !streamingMsg?.reasoningContent && (
        <div style={styles.typing}>
          <span className="typing-dot" />
          <span className="typing-dot" />
          <span className="typing-dot" />
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  );
}

const styles = {
  container: {
    flex: 1,
    overflowY: 'auto',
    padding: '12px 14px',
    display: 'flex',
    flexDirection: 'column',
    gap: 10,
  },
  empty: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    flex: 1,
    minHeight: 200,
    gap: 8,
  },
  emptyIcon: {
    width: 40,
    height: 40,
    borderRadius: 10,
    background: 'rgba(94,156,245,0.12)',
    color: '#58a6ff',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: 20,
    fontWeight: 700,
  },
  emptyTitle: {
    fontSize: 15,
    fontWeight: 600,
    color: 'var(--text-primary, #c9cdd4)',
  },
  emptySub: {
    fontSize: 12,
    color: 'var(--text-muted, #5a606b)',
  },
  typing: {
    alignSelf: 'flex-start',
    padding: '10px 14px',
    background: 'var(--bg-elevated, #1f2530)',
    borderRadius: 8,
    display: 'flex',
    gap: 4,
  },
};
