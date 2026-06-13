import { useState } from 'react';
import PropertiesPanel from './PropertiesPanel';
import ChatPanel from './ChatPanel';
import RunPanel from './RunPanel';

/**
 * 右侧面板 — 属性 / 对话 / 运行 三 Tab，支持拖拽宽度、收起、Markdown 渲染。
 */
export default function RightPanel({
  selectedNode, nodes, setNodes, edges, name, variables,
  panelWidth, collapsed, onToggleCollapse, setNodeStatuses,
}) {
  const [activeTab, setActiveTab] = useState('properties');

  const tabs = [
    { key: 'properties', label: '属性' },
    { key: 'chat', label: '对话' },
    { key: 'run', label: '运行' },
  ];

  if (collapsed) {
    return (
      <div style={styles.collapsedBar} onClick={onToggleCollapse} title="展开属性面板">
        <span style={styles.collapsedText}>属性</span>
        <span style={styles.collapsedIcon}>◀</span>
      </div>
    );
  }

  return (
    <div style={{ ...styles.container, width: panelWidth, minWidth: panelWidth }}>
      {/* Tab 栏 */}
      <div style={styles.tabBar}>
        {tabs.map((t) => (
          <button
            key={t.key}
            style={{ ...styles.tab, ...(activeTab === t.key ? styles.tabActive : {}) }}
            onClick={() => setActiveTab(t.key)}
          >
            {t.label}
          </button>
        ))}
        <button style={styles.collapseBtn} onClick={onToggleCollapse} title="收起面板">
          ▶
        </button>
      </div>

      {/* Tab 内容 */}
      <div style={styles.tabContent}>
        {activeTab === 'properties' && (
          <PropertiesPanel selectedNode={selectedNode} nodes={nodes} setNodes={setNodes} />
        )}
        {activeTab === 'chat' && (
          <ChatPanel selectedNode={selectedNode} />
        )}
        {activeTab === 'run' && (
          <RunPanel nodes={nodes} edges={edges} name={name} variables={variables} setNodeStatuses={setNodeStatuses} />
        )}
      </div>
    </div>
  );
}

const styles = {
  container: {
    height: '100%',
    background: '#12161e',
    borderLeft: '1px solid #222833',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    fontSize: 13,
    color: '#c9cdd4',
  },
  collapsedBar: {
    width: 30,
    minWidth: 30,
    height: '100%',
    background: '#12161e',
    borderLeft: '1px solid #222833',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    cursor: 'pointer',
    color: '#5a606b',
    writingMode: 'vertical-rl',
    fontSize: 11,
    fontWeight: 600,
    letterSpacing: 2,
  },
  collapsedText: { marginBottom: 4 },
  collapsedIcon: { fontSize: 10 },
  tabBar: {
    display: 'flex',
    borderBottom: '1px solid #222833',
    background: '#191e28',
  },
  collapseBtn: {
    background: 'transparent',
    color: '#5a606b',
    fontSize: 11,
    padding: '0 10px',
    marginLeft: 'auto',
  },
  tab: {
    flex: 1,
    padding: '9px 6px',
    background: 'transparent',
    color: '#8b919b',
    border: 'none',
    cursor: 'pointer',
    fontSize: 12,
    fontWeight: 600,
    borderBottom: '2px solid transparent',
    transition: 'all 0.15s',
  },
  tabActive: {
    color: '#c9cdd4',
    borderBottomColor: '#5e9cf5',
  },
  tabContent: {
    flex: 1,
    overflowY: 'auto',
  },
};
