import { useState, useMemo } from 'react';
import { getAllCategories, getNodeDefsByCategory, CATEGORY_LABEL_COLORS } from '../nodes/nodeRegistry';

/** 分类中文名映射 */
const CATEGORY_NAMES_CN = {
  Action: '动作',
  Composite: '组合',
};

/**
 * 左侧节点面板 — 按分类展示所有可用节点，支持折叠分类、搜索过滤、拖拽到画布、整体收起。
 */
export default function NodePalette({ collapsed, onToggleCollapse }) {
  const categories = getAllCategories();
  const [collapsedCats, setCollapsedCats] = useState({});
  const [search, setSearch] = useState('');

  const toggleCat = (cat) => {
    setCollapsedCats((prev) => ({ ...prev, [cat]: !prev[cat] }));
  };

  const handleDragStart = (event, nodeType) => {
    event.dataTransfer.setData('application/workflow-node-type', nodeType);
    event.dataTransfer.effectAllowed = 'move';
  };

  const filteredCategories = useMemo(() => {
    const q = search.toLowerCase().trim();
    return categories.map((cat) => {
      const defs = getNodeDefsByCategory(cat);
      const filtered = q
        ? defs.filter((d) =>
            d.displayName.toLowerCase().includes(q) ||
            d.nodeType.toLowerCase().includes(q) ||
            (d.description && d.description.toLowerCase().includes(q))
          )
        : defs;
      return { cat, defs: filtered };
    }).filter(({ defs }) => defs.length > 0);
  }, [categories, search]);

  const totalCount = useMemo(
    () => filteredCategories.reduce((sum, { defs }) => sum + defs.length, 0),
    [filteredCategories]
  );

  if (collapsed) {
    return (
      <div style={styles.collapsedBar} onClick={onToggleCollapse} title="展开节点面板">
        <span style={styles.collapsedIcon}>▶</span>
        <span style={styles.collapsedText}>节点</span>
      </div>
    );
  }

  return (
    <div style={styles.container}>
      {/* 头部 */}
      <div style={styles.header}>
        <span style={styles.headerTitle}>节点面板</span>
        <button style={styles.collapseBtn} onClick={onToggleCollapse} title="收起面板">
          ◀
        </button>
      </div>

      {/* 搜索 */}
      <div style={styles.searchBox}>
        <input
          style={styles.searchInput}
          type="text"
          placeholder="搜索节点…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        {search && (
          <span style={styles.searchCount}>{totalCount} 个</span>
        )}
      </div>

      {/* 列表 */}
      <div style={styles.list}>
        {filteredCategories.map(({ cat, defs }) => {
          const isCollapsed = collapsedCats[cat];
          const labelColor = CATEGORY_LABEL_COLORS[cat] || '#888';
          return (
            <div key={cat}>
              <div
                style={styles.categoryHeader}
                onClick={() => toggleCat(cat)}
              >
                <span style={{ ...styles.catArrow, transform: isCollapsed ? 'rotate(-90deg)' : 'rotate(0deg)' }}>
                  ▼
                </span>
                <span style={{ ...styles.catDot, background: labelColor }} />
                <span style={styles.catName}>{CATEGORY_NAMES_CN[cat] || cat}</span>
                <span style={styles.catCount}>{defs.length}</span>
              </div>
              {!isCollapsed && defs.map((def) => (
                <div
                  key={def.nodeType}
                  className="palette-item"
                  style={styles.item}
                  draggable
                  onDragStart={(e) => handleDragStart(e, def.nodeType)}
                  title={def.description || def.displayName}
                >
                  <span style={{ ...styles.dot, background: labelColor }} />
                  <span style={styles.itemName}>{def.displayName}</span>
                  {def.description && (
                    <span style={styles.itemDesc}>{def.description}</span>
                  )}
                </div>
              ))}
            </div>
          );
        })}
        {filteredCategories.length === 0 && (
          <div style={styles.empty}>无匹配节点</div>
        )}
      </div>
    </div>
  );
}

const styles = {
  container: {
    width: 'var(--sidebar-width, 240px)',
    minWidth: 'var(--sidebar-width, 240px)',
    height: '100%',
    background: 'var(--bg-panel, #12161e)',
    borderRight: '1px solid var(--border, #222833)',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    fontSize: 13,
    color: 'var(--text-primary, #c9cdd4)',
  },
  collapsedBar: {
    width: 32,
    minWidth: 32,
    height: '100%',
    background: 'var(--bg-panel, #12161e)',
    borderRight: '1px solid var(--border, #222833)',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    paddingTop: 12,
    gap: 6,
    cursor: 'pointer',
    color: 'var(--text-muted, #5a606b)',
    transition: 'color 0.15s',
    writingMode: 'vertical-rl',
  },
  collapsedIcon: { fontSize: 10 },
  collapsedText: { fontSize: 11, fontWeight: 600, letterSpacing: 2 },
  header: {
    padding: '10px 14px',
    fontWeight: 700,
    fontSize: 14,
    color: 'var(--text-primary, #c9cdd4)',
    borderBottom: '1px solid var(--border, #222833)',
    background: 'var(--bg-surface, #191e28)',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  headerTitle: { flex: 1 },
  collapseBtn: {
    background: 'transparent',
    color: 'var(--text-muted, #5a606b)',
    fontSize: 12,
    padding: '2px 6px',
    borderRadius: 4,
  },
  searchBox: {
    padding: '8px 12px',
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    borderBottom: '1px solid var(--border, #222833)',
  },
  searchInput: {
    flex: 1,
    padding: '5px 8px',
    fontSize: 12,
    borderRadius: 6,
    background: 'var(--bg-input, #151a24)',
    border: '1px solid var(--border, #222833)',
    color: 'var(--text-primary, #c9cdd4)',
    outline: 'none',
  },
  searchCount: {
    fontSize: 11,
    color: 'var(--text-muted, #5a606b)',
    whiteSpace: 'nowrap',
  },
  list: {
    flex: 1,
    overflowY: 'auto',
    paddingBottom: 8,
  },
  categoryHeader: {
    padding: '7px 14px',
    fontWeight: 700,
    fontSize: 11,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    color: 'var(--text-secondary, #8b919b)',
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    cursor: 'pointer',
    userSelect: 'none',
    transition: 'background 0.1s',
    borderBottom: '1px solid var(--border, #222833)',
  },
  catArrow: {
    fontSize: 8,
    transition: 'transform 0.2s var(--ease-out, ease)',
    opacity: 0.5,
  },
  catDot: {
    width: 6,
    height: 6,
    borderRadius: '50%',
    flexShrink: 0,
  },
  catName: { flex: 1 },
  catCount: {
    fontSize: 10,
    color: 'var(--text-muted, #5a606b)',
    fontWeight: 400,
  },
  item: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    padding: '8px 14px 8px 28px',
    cursor: 'grab',
    borderBottom: '1px solid rgba(255,255,255,0.02)',
    transition: 'background 0.1s',
  },
  dot: {
    width: 7,
    height: 7,
    borderRadius: '50%',
    flexShrink: 0,
    opacity: 0.7,
  },
  itemName: {
    fontWeight: 600,
    color: 'var(--text-primary, #c9cdd4)',
    whiteSpace: 'nowrap',
    fontSize: 12,
  },
  itemDesc: {
    fontSize: 10,
    color: 'var(--text-muted, #5a606b)',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    marginLeft: 'auto',
  },
  empty: {
    padding: 24,
    textAlign: 'center',
    color: 'var(--text-muted, #5a606b)',
    fontSize: 12,
  },
};
