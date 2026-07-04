import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';
import ThinkingBlock from './ThinkingBlock';
import ToolCallCard from './ToolCallCard';

const MemoMarkdown = React.memo(function Markdown({ content }) {
  return (
    <div className="md-content">
      <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>
        {content}
      </ReactMarkdown>
    </div>
  );
});

export default function MessageBubble({ msg }) {
  const isUser = msg.role === 'user';
  const isError = msg.role === 'error';
  const isAssistant = msg.role === 'assistant';
  const isStreaming = msg._streaming;

  const bubbleStyle = {
    ...styles.bubble,
    alignSelf: isUser ? 'flex-end' : 'flex-start',
    background: isUser
      ? 'var(--bubble-user-bg, #1a3a2a)'
      : isError
        ? 'var(--bubble-error-bg, #2e1a1c)'
        : 'var(--bubble-ai-bg, #161b22)',
    borderColor: isUser
      ? 'var(--bubble-user-border, #234d38)'
      : isError
        ? 'var(--bubble-error-border, #f2555a44)'
        : 'var(--bubble-ai-border, #30363d)',
    maxWidth: isUser ? '82%' : '94%',
  };

  return (
    <div style={bubbleStyle}>
      {/* Role label */}
      <div style={styles.role(isUser, isError)}>
        {isUser ? 'You' : isError ? 'Error' : 'Assistant'}
      </div>

      {/* Thinking */}
      {isAssistant && msg.reasoningContent && (
        <ThinkingBlock content={msg.reasoningContent} />
      )}

      {/* Tool calls */}
      {isAssistant && msg.toolCalls?.length > 0 && (
        <div style={styles.toolCallsWrap}>
          {msg.toolCalls.map((tc, i) => (
            <ToolCallCard key={tc.id || i} tool={tc} />
          ))}
        </div>
      )}

      {/* Content */}
      {isAssistant && !msg.content && isStreaming && (
        <span style={styles.streamingHint}>Thinking...</span>
      )}
      {msg.content ? (
        <MemoMarkdown content={msg.content} />
      ) : isAssistant ? null : (
        <span>{msg.content}</span>
      )}

      {/* Streaming cursor */}
      {isStreaming && msg.content && (
        <span className="streaming-cursor" />
      )}
    </div>
  );
}

const styles = {
  bubble: {
    padding: '10px 12px',
    borderRadius: 8,
    border: '1px solid',
    wordBreak: 'break-word',
    fontSize: 12.5,
    lineHeight: 1.6,
  },
  role: (isUser, isError) => ({
    fontSize: 10,
    fontWeight: 700,
    marginBottom: 5,
    opacity: 0.55,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    color: isUser ? '#3fb950' : isError ? '#f2555a' : '#58a6ff',
  }),
  toolCallsWrap: {
    display: 'flex',
    flexDirection: 'column',
    gap: 6,
    marginBottom: 8,
  },
  streamingHint: {
    color: 'var(--text-muted, #5a606b)',
    fontStyle: 'italic',
    fontSize: 11,
  },
};
