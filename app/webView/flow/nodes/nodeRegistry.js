/**
 * 节点类型注册表 —— 从 Python 端 NodeRegistry.GetAllNodeInfo() 动态拉取。
 * 所有节点类型定义由后端统一管理，前端不硬编码节点列表。
 */

export const ENodeCategory = {
  ACTION: 'ACTION',
  COMPOSITE: 'COMPOSITE',
};

/** 分类颜色（低饱和度科技风） */
export const CATEGORY_COLORS = {
  [ENodeCategory.ACTION]: '#3ecf8e',
  [ENodeCategory.COMPOSITE]: '#5e9cf5',
};

/** 分类头部背景 */
export const CATEGORY_HEADER_COLORS = {
  [ENodeCategory.ACTION]: '#1a332a',
  [ENodeCategory.COMPOSITE]: '#1a2433',
};

/** 分类标签文字色 */
export const CATEGORY_LABEL_COLORS = {
  [ENodeCategory.ACTION]: '#3ecf8e',
  [ENodeCategory.COMPOSITE]: '#5e9cf5',
};

/** 参数类型颜色映射 */
export const CONFIG_TYPE_COLORS = {
  string: '#c98bdb',
  int: '#5e9cf5',
  float: '#5e9cf5',
  bool: '#f2555a',
};

// ==================== 内部状态 ====================

/** @type {Record<string, NodeTypeDef>} */
let NODE_TYPES = {};
let _initialized = false;
let _initPromise = null;

// ==================== 初始化 ====================

/**
 * 从后端拉取节点定义，填充本地注册表。
 * 应在 App 启动时调用一次，可重复调用（幂等）。
 * @returns {Promise<void>}
 */
export async function initNodeRegistry() {
  if (_initialized) return;
  if (_initPromise) return _initPromise;

  _initPromise = (async () => {
    try {
      const resp = await fetch('/api/nodes');
      if (!resp.ok) {
        throw new Error(`Failed to fetch node definitions: ${resp.status}`);
      }
      const data = await resp.json();
      const nodes = data.nodes || [];

      const map = {};
      for (const def of nodes) {
        map[def.nodeType] = def;
      }
      NODE_TYPES = map;
      _initialized = true;
    } catch (err) {
      _initPromise = null;  // 失败时清除缓存，允许后续重试
      throw err;
    }
  })();

  return _initPromise;
}

// ==================== 查询 API ====================

export function getNodeDef(nodeType) {
  return NODE_TYPES[nodeType] || null;
}

export function getAllNodeDefs() {
  return Object.values(NODE_TYPES);
}

export function getNodeDefsByCategory(category) {
  return Object.values(NODE_TYPES).filter((d) => d.category === category);
}

export function getAllCategories() {
  return [ENodeCategory.ACTION, ENodeCategory.COMPOSITE];
}

export function isReady() {
  return _initialized;
}
