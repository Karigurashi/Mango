export default function TokenFooter({ msg }) {
  if (!msg) return null;

  const { promptTokens, completionTokens, cacheHitRate } = msg;

  return (
    <div style={styles.footer}>
      <span style={styles.token}>
        <span style={styles.label}>In</span>
        <span style={styles.value}>{formatK(promptTokens || 0)}</span>
      </span>
      <span style={styles.token}>
        <span style={styles.label}>Out</span>
        <span style={styles.value}>{formatK(completionTokens || 0)}</span>
      </span>
      {cacheHitRate > 0 && (
        <span style={styles.token}>
          <span style={styles.label}>Cache</span>
          <span style={{ ...styles.value, color: '#d29922' }}>
            {cacheHitRate.toFixed(1)}%
          </span>
        </span>
      )}
    </div>
  );
}

function formatK(v) {
  if (v >= 1000) return `${(v / 1000).toFixed(1)}k`;
  return String(v);
}

const styles = {
  footer: {
    display: 'flex',
    alignItems: 'center',
    gap: 14,
    padding: '4px 14px',
    borderTop: '1px solid var(--border, #222833)',
    background: 'var(--bg-panel, #161b22)',
    flexShrink: 0,
  },
  token: {
    display: 'flex',
    alignItems: 'center',
    gap: 4,
    fontSize: 10.5,
  },
  label: {
    color: 'var(--text-muted, #5a606b)',
    textTransform: 'uppercase',
    fontWeight: 600,
    fontSize: 9,
  },
  value: {
    color: 'var(--text-secondary, #8b919b)',
    fontWeight: 600,
  },
};
