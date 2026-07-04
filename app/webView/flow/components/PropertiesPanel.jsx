import { useState, useEffect, useRef, useMemo } from 'react';
import { getNodeDef, CATEGORY_LABEL_COLORS } from '../nodes/nodeRegistry';

/**
 * 属性面板 — 编辑选中节点的名称和配置参数。
 */
export default function PropertiesPanel({ selectedNode, nodes, setNodes }) {
  const [localConfig, setLocalConfig] = useState({});
  const [localName, setLocalName] = useState('');
  const prevNodeRef = useRef(null);

  useEffect(() => {
    if (selectedNode && selectedNode !== prevNodeRef.current) {
      prevNodeRef.current = selectedNode;
      setLocalConfig({ ...(selectedNode.data.config || {}) });
      setLocalName(selectedNode.data.name || '');
    } else if (!selectedNode) {
      prevNodeRef.current = null;
      setLocalConfig({});
      setLocalName('');
    }
  }, [selectedNode]);

  const nodeDef = useMemo(
    () => (selectedNode ? getNodeDef(selectedNode.data.nodeType) : null),
    [selectedNode?.data?.nodeType]
  );

  if (!selectedNode) {
    return <div style={styles.empty}>选中一个节点以编辑参数</div>;
  }

  if (!nodeDef) {
    return <div style={styles.empty}>未知节点类型</div>;
  }

  const configFields = nodeDef.configSchema || [];
  const labelColor = CATEGORY_LABEL_COLORS[nodeDef.category] || '#5e9cf5';

  const handleNameChange = (value) => {
    setLocalName(value);
    setNodes((nds) =>
      nds.map((n) =>
        n.id === selectedNode.id
          ? { ...n, data: { ...n.data, name: value || null } }
          : n
      )
    );
  };

  const handleChange = (fieldName, value) => {
    const newConfig = { ...localConfig, [fieldName]: value };
    setLocalConfig(newConfig);
    setNodes((nds) =>
      nds.map((n) =>
        n.id === selectedNode.id
          ? { ...n, data: { ...n.data, config: newConfig } }
          : n
      )
    );
  };

  const renderInput = (field) => {
    const value = localConfig[field.name] ?? field.default ?? '';
    const s = { ...styles.propInput };

    switch (field.type) {
      case 'bool':
        return (
          <select style={s} value={value === true || value === 'true' ? 'true' : 'false'}
            onChange={(e) => handleChange(field.name, e.target.value === 'true')}>
            <option value="true">True</option>
            <option value="false">False</option>
          </select>
        );
      case 'int':
        return (
          <input type="number" step="1" style={s} value={value}
            onChange={(e) => handleChange(field.name, e.target.value === '' ? '' : parseInt(e.target.value, 10))} />
        );
      case 'float':
        return (
          <input type="number" step="0.1" style={s} value={value}
            onChange={(e) => handleChange(field.name, e.target.value === '' ? '' : parseFloat(e.target.value))} />
        );
      default:
        return (
          <input type="text" style={s} value={value}
            onChange={(e) => handleChange(field.name, e.target.value)} />
        );
    }
  };

  return (
    <div>
      {/* 节点信息 */}
      <div style={styles.section}>
        <div style={styles.sectionTitle}>
          <span style={{ ...styles.categoryBadge, background: labelColor + '22', color: labelColor, border: `1px solid ${labelColor}44` }}>
            {nodeDef.category}
          </span>
          {nodeDef.displayName}
        </div>
        <div style={styles.infoRow}>
          <span style={styles.infoLabel}>ID</span>
          <code style={styles.mono}>{selectedNode.id}</code>
        </div>
        <div style={styles.infoRow}>
          <span style={styles.infoLabel}>类型</span>
          <code style={styles.mono}>{selectedNode.data.nodeType}</code>
        </div>
        <div style={styles.desc}>{nodeDef.description}</div>
      </div>

      {/* 节点名称 */}
      <div style={styles.section}>
        <div style={styles.sectionLabel}>节点名称</div>
        <input
          type="text"
          style={styles.propInput}
          placeholder={nodeDef.displayName}
          value={localName}
          onChange={(e) => handleNameChange(e.target.value)}
        />
        <div style={{ fontSize: 10, color: '#5a606b', marginTop: 4 }}>
          留空则使用默认名称「{nodeDef.displayName}」
        </div>
      </div>

      {/* 可配置参数 */}
      {configFields.length > 0 && (
        <div style={styles.section}>
          <div style={styles.sectionLabel}>配置参数</div>
          {configFields.map((f) => (
            <div key={f.name} style={styles.editRow}>
              <label style={styles.editLabel} title={f.description}>
                {f.name}
                <span style={styles.editType}>{f.type}</span>
              </label>
              {renderInput(f)}
            </div>
          ))}
        </div>
      )}

      {configFields.length === 0 && (
        <div style={styles.section}>
          <div style={styles.emptySm}>此节点无可配置参数</div>
        </div>
      )}
    </div>
  );
}

const styles = {
  empty: {
    padding: 24,
    color: '#5a606b',
    textAlign: 'center',
    fontSize: 13,
  },
  emptySm: {
    color: '#5a606b',
    textAlign: 'center',
    fontSize: 12,
    padding: '8px 0',
  },
  section: {
    padding: '12px 14px',
    borderBottom: '1px solid #1a1f2b',
  },
  sectionTitle: {
    fontSize: 14,
    fontWeight: 700,
    color: '#c9cdd4',
    marginBottom: 8,
    display: 'flex',
    alignItems: 'center',
    gap: 8,
  },
  sectionLabel: {
    fontSize: 11,
    fontWeight: 700,
    textTransform: 'uppercase',
    color: '#8b919b',
    marginBottom: 8,
    letterSpacing: 0.5,
  },
  categoryBadge: {
    display: 'inline-block',
    padding: '2px 7px',
    borderRadius: 4,
    fontSize: 10,
    fontWeight: 700,
    textTransform: 'uppercase',
  },
  infoRow: {
    display: 'flex',
    justifyContent: 'space-between',
    marginBottom: 3,
  },
  infoLabel: { color: '#8b919b', fontSize: 11 },
  mono: {
    fontFamily: "'JetBrains Mono', 'Consolas', monospace",
    fontSize: 11,
    color: '#8b919b',
  },
  desc: {
    fontSize: 11,
    color: '#5a606b',
    marginTop: 6,
    fontStyle: 'italic',
  },
  editRow: { marginBottom: 8 },
  editLabel: {
    fontSize: 11,
    color: '#8b919b',
    marginBottom: 3,
    display: 'flex',
    alignItems: 'center',
    gap: 6,
  },
  editType: {
    fontSize: 9,
    color: '#5a606b',
    fontFamily: "'JetBrains Mono', monospace",
    textTransform: 'uppercase',
  },
  propInput: {
    width: '100%',
    padding: '6px 8px',
    background: '#151a24',
    border: '1px solid #222833',
    borderRadius: 6,
    fontSize: 12,
    fontFamily: "'JetBrains Mono', 'Consolas', monospace",
    outline: 'none',
    color: '#c9cdd4',
    transition: 'border-color 0.15s',
    boxSizing: 'border-box',
  },
};
