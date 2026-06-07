import { useRef, useState } from 'react';
import { downloadJson, jsonToFlow } from '../utils/workflowIO';

/**
 * 顶部工具栏 — 新建、导入、导出、蓝图命名、状态信息。
 */
export default function Toolbar({ nodes, edges, name, setNodes, setEdges, setName, variables, setVariables }) {
  const fileInputRef = useRef(null);
  const [nameEditing, setNameEditing] = useState(false);
  const [nameDraft, setNameDraft] = useState(name);

  const handleNew = () => {
    if (nodes.length > 0 || edges.length > 0) {
      if (!window.confirm('新建工作流将清空当前内容，是否继续？')) return;
    }
    setNodes([]);
    setEdges([]);
    setName('');
    setVariables({});
  };

  const handleExport = () => {
    const exportName = name || window.prompt('请输入工作流名称：', 'Workflow') || 'Workflow';
    setName(exportName);
    downloadJson(nodes, edges, exportName, variables);
  };

  const handleImport = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (evt) => {
      try {
        const json = JSON.parse(evt.target.result);
        const { nodes: newNodes, edges: newEdges, name: bpName, variables: bpVars } = jsonToFlow(json);
        setNodes(newNodes);
        setEdges(newEdges);
        setName(bpName || '');
        setVariables(bpVars || {});
      } catch (err) {
        alert('JSON 解析失败：' + err.message);
      }
    };
    reader.readAsText(file);
    e.target.value = '';
  };

  const handleNameSubmit = () => {
    setName(nameDraft);
    setNameEditing(false);
  };

  return (
    <div style={styles.toolbar}>
      {/* 蓝图名称 */}
      <div style={styles.nameSection}>
        {nameEditing ? (
          <input
            style={styles.nameInput}
            value={nameDraft}
            onChange={(e) => setNameDraft(e.target.value)}
            onBlur={handleNameSubmit}
            onKeyDown={(e) => e.key === 'Enter' && handleNameSubmit()}
            autoFocus
          />
        ) : (
          <span
            style={styles.nameDisplay}
            onClick={() => {
              setNameDraft(name);
              setNameEditing(true);
            }}
            title="点击编辑名称"
          >
            {name || '未命名工作流'}
          </span>
        )}
      </div>

      {/* 操作按钮 */}
      <div style={styles.actions}>
        <button style={styles.btn} onClick={handleNew} title="新建工作流">
          新建
        </button>
        <button style={styles.btn} onClick={handleImport} title="从 JSON 文件导入">
          导入
        </button>
        <button
          style={{ ...styles.btn, ...styles.btnExport }}
          onClick={handleExport}
          title="导出为 JSON 文件"
        >
          导出
        </button>
      </div>

      {/* 状态信息 */}
      <div style={styles.status}>
        <span>节点 {nodes.length}</span>
        <span style={{ marginLeft: 14 }}>连线 {edges.length}</span>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept=".json"
        style={{ display: 'none' }}
        onChange={handleFileChange}
      />
    </div>
  );
}

const s = {
  toolbar: {
    height: 44,
    minHeight: 44,
    background: '#12161e',
    borderBottom: '1px solid #222833',
    display: 'flex',
    alignItems: 'center',
    padding: '0 16px',
    gap: 14,
  },
  nameSection: { flex: 1 },
  nameDisplay: {
    fontSize: 14,
    fontWeight: 700,
    color: '#c9cdd4',
    cursor: 'pointer',
    padding: '3px 8px',
    borderRadius: 6,
    transition: 'background 0.12s',
  },
  nameInput: {
    fontSize: 14,
    fontWeight: 700,
    color: '#c9cdd4',
    background: '#151a24',
    border: '1px solid #3d5a8a',
    borderRadius: 6,
    padding: '3px 8px',
    outline: 'none',
    width: 240,
  },
  actions: { display: 'flex', gap: 6 },
  btn: {
    padding: '6px 14px',
    background: '#1f2530',
    color: '#c9cdd4',
    border: '1px solid #252b36',
    borderRadius: 6,
    cursor: 'pointer',
    fontSize: 12,
    fontWeight: 600,
    whiteSpace: 'nowrap',
    transition: 'all 0.12s',
  },
  btnExport: {
    background: '#1a332a',
    borderColor: '#234d38',
    color: '#3ecf8e',
  },
  status: {
    fontSize: 11,
    color: '#5a606b',
    whiteSpace: 'nowrap',
    fontWeight: 500,
  },
};

const styles = s;
