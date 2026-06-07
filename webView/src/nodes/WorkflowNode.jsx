import { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import { getNodeDef, CATEGORY_HEADER_COLORS, CATEGORY_LABEL_COLORS, CONFIG_TYPE_COLORS } from './nodeRegistry';
import { EExecutionStatus } from '../components/Canvas';

/** 分类 → 节点 ID 徽章图标 */
const CATEGORY_ICONS = {
  Action: '▶',
  Condition: '◇',
  Composite: '⊞',
};

/**
 * 自定义 React Flow 节点 — 低饱和度现代科技风。
 */
const WorkflowNode = memo(({ id, data, selected }) => {
  const nodeType = data.nodeType;
  const def = getNodeDef(nodeType);
  if (!def) {
    return (
      <div style={{
        background: 'var(--bg-elevated, #1f2530)',
        color: 'var(--error, #f2555a)',
        padding: '8px 12px',
        borderRadius: 8,
        fontSize: 12,
        border: '1px solid var(--error, #f2555a)',
      }}>
        Unknown: {nodeType}
      </div>
    );
  }

  const headerBg = CATEGORY_HEADER_COLORS[def.category] || '#1a2433';
  const labelColor = CATEGORY_LABEL_COLORS[def.category] || '#5e9cf5';
  const glowColor = CATEGORY_LABEL_COLORS[def.category] || '#5e9cf5';
  const catIcon = CATEGORY_ICONS[def.category] || '●';

  // 节点显示名称：用户自定义 name > displayName
  const nodeName = data.name || def.displayName;

  // 执行状态：running / completed / failed / cancelled
  const execStatus = data.__status;

  // 根据选中 + 执行状态决定边框与光晕
  let borderStyle;
  let boxShadowStyle;
  if (selected) {
    borderStyle = `1.5px solid ${glowColor}`;
    boxShadowStyle = `0 0 18px ${glowColor}33, 0 4px 16px rgba(0,0,0,0.5)`;
  } else if (execStatus === EExecutionStatus.RUNNING) {
    borderStyle = '2px solid #e6b450';
    boxShadowStyle = '0 0 18px rgba(230, 180, 80, 0.55), 0 4px 16px rgba(0,0,0,0.5)';
  } else if (execStatus === EExecutionStatus.COMPLETED) {
    borderStyle = '1.5px solid #3ecf8e';
    boxShadowStyle = '0 0 12px rgba(62, 207, 142, 0.35), 0 2px 8px rgba(0,0,0,0.4)';
  } else if (execStatus === EExecutionStatus.FAILED) {
    borderStyle = '1.5px solid #f2555a';
    boxShadowStyle = '0 0 16px rgba(242, 85, 90, 0.45), 0 4px 16px rgba(0,0,0,0.5)';
  } else {
    borderStyle = '1px solid #252b36';
    boxShadowStyle = '0 2px 8px rgba(0,0,0,0.4)';
  }

  const config = data.config || {};
  const configFields = def.configSchema || [];
  const visibleConfigs = configFields.filter(
    (f) => config[f.name] !== undefined && config[f.name] !== '' && config[f.name] !== f.default
  );

  return (
    <div
      className={
        execStatus === EExecutionStatus.RUNNING ? 'node-running' :
        execStatus === EExecutionStatus.COMPLETED ? 'node-completed' :
        execStatus === EExecutionStatus.FAILED ? 'node-failed' : ''
      }
      style={{
        background: '#191e28',
        borderRadius: 9,
        minWidth: 170,
        border: borderStyle,
        boxShadow: boxShadowStyle,
        fontFamily: 'inherit',
        fontSize: 13,
        color: 'var(--text-primary, #c9cdd4)',
        overflow: 'hidden',
        transition: 'border-color 0.15s ease, box-shadow 0.15s ease',
        position: 'relative',
      }}
    >
      {/* 头部 */}
      <div
        style={{
          background: headerBg,
          padding: '6px 10px',
          fontWeight: 600,
          fontSize: 13,
          color: 'var(--text-primary, #c9cdd4)',
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          borderBottom: '1px solid rgba(255,255,255,0.04)',
        }}
      >
        {/* 节点 ID 标识 */}
        <span style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 2,
          padding: '1px 5px',
          background: 'rgba(0,0,0,0.22)',
          borderRadius: 3,
          fontSize: 9,
          fontWeight: 600,
          color: labelColor,
          fontFamily: "'JetBrains Mono', 'Consolas', monospace",
          opacity: 0.7,
          userSelect: 'none',
          lineHeight: 1.4,
          flexShrink: 0,
        }}>
          <span style={{ fontSize: 9 }}>{catIcon}</span>
          <span>{id}</span>
        </span>
        <span style={{
          fontSize: 10,
          fontWeight: 700,
          color: labelColor,
          textTransform: 'uppercase',
          letterSpacing: 0.6,
          opacity: 0.85,
        }}>
          {def.category}
        </span>
        <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{nodeName}</span>
      </div>

      {/* 配置摘要 —— 逐行展示，长值自动换行 */}
      {visibleConfigs.length > 0 && (
        <div
          style={{
            padding: '6px 12px 8px',
            fontSize: 10,
            color: 'var(--text-muted, #5a606b)',
            fontFamily: "'JetBrains Mono', 'Consolas', monospace",
            lineHeight: 1.6,
          }}
        >
          {visibleConfigs.map((f) => {
            const typeColor = CONFIG_TYPE_COLORS[f.type] || '#8b919b';
            const rawValue = config[f.name];
            const displayValue = typeof rawValue === 'boolean'
              ? String(rawValue)
              : String(rawValue);
            return (
              <div
                key={f.name}
                style={{
                  wordBreak: 'break-word',
                  overflowWrap: 'break-word',
                  marginBottom: 2,
                }}
              >
                <span style={{ color: typeColor, fontWeight: 500 }}>{f.name}</span>
                <span style={{ color: '#5a606b', margin: '0 3px' }}>=</span>
                <span style={{ color: '#8b919b' }}>
                  {displayValue.length > 40
                    ? displayValue.slice(0, 40) + '…'
                    : displayValue}
                </span>
              </div>
            );
          })}
        </div>
      )}

      {/* Handle：OUT边从右侧连出/入，SUB_NODE边从下方连出、上方入 */}
      <Handle type="target" position={Position.Left} id="target-out"
        style={{ opacity: 0, width: 1, height: 1 }} />
      <Handle type="target" position={Position.Top} id="target-sub"
        style={{ opacity: 0, width: 1, height: 1 }} />
      <Handle type="source" position={Position.Right} id="source-out"
        style={{ opacity: 0, width: 1, height: 1 }} />
      <Handle type="source" position={Position.Bottom} id="source-sub"
        style={{ opacity: 0, width: 1, height: 1 }} />
    </div>
  );
});

export default WorkflowNode;
