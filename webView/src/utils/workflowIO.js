import { getNodeDef } from '../nodes/nodeRegistry';

let _nodeIdCounter = 0;

/** 生成唯一节点 ID（int），React Flow 使用时需 String() 转换。 */
export function generateNodeId() {
  _nodeIdCounter++;
  return _nodeIdCounter;
}

/**
 * 从 Workflow JSON 转换为 React Flow 的 nodes + edges。
 * JSON 中节点 ID 为 int，React Flow 要求 string，此处做转换。
 * @param {Object} jsonData - { name, variables?, nodes, edges }
 * @returns {{ nodes: Object[], edges: Object[] }}
 */
export function jsonToFlow(jsonData) {
  const nodes = [];
  const edges = [];
  const idMap = new Map();

  // 处理节点
  for (const nodeData of jsonData.nodes || []) {
    const def = getNodeDef(nodeData.type);
    if (!def) {
      console.warn(`Unknown node type: ${nodeData.type}, skipping node ${nodeData.id}`);
      continue;
    }

    // 同步计数器：取已导入的最大 ID
    const numId = typeof nodeData.id === 'number' ? nodeData.id : parseInt(nodeData.id, 10);
    if (!isNaN(numId) && numId > _nodeIdCounter) {
      _nodeIdCounter = numId;
    }

    const strId = String(numId);
    idMap.set(nodeData.id, strId);

    nodes.push({
      id: strId,
      type: 'workflowNode',
      position: { x: nodeData.x || 0, y: nodeData.y || 0 },
      data: {
        nodeType: nodeData.type,
        name: nodeData.name || null,
        config: { ...(nodeData.config || {}) },
      },
    });
  }

  // 处理边（兼容 connections 和 edges 两种字段名）
  const edgeList = jsonData.edges || jsonData.connections || [];
  for (const edge of edgeList) {
    const fromRaw = typeof edge.from === 'object' ? (edge.from.nodeId || edge.from) : edge.from;
    const toRaw = typeof edge.to === 'object' ? (edge.to.nodeId || edge.to) : edge.to;
    const fromNodeId = String(typeof fromRaw === 'number' ? fromRaw : parseInt(fromRaw, 10));
    const toNodeId = String(typeof toRaw === 'number' ? toRaw : parseInt(toRaw, 10));

    // edgeType: OUT=0(蓝,右侧), SUB_NODE=1(紫,下方)
    const edgeType = edge.type || 0;
    const isSubNode = edgeType === 1;
    const stroke = isSubNode ? '#c98bdb' : '#5e9cf5';

    edges.push({
      id: `e-${fromNodeId}-${toNodeId}`,
      source: fromNodeId,
      target: toNodeId,
      sourceHandle: isSubNode ? 'source-sub' : 'source-out',
      targetHandle: isSubNode ? 'target-sub' : 'target-out',
      type: 'default',
      animated: false,
      style: { stroke, strokeWidth: 1.5 },
      markerEnd: { type: 'arrowclosed', color: stroke, width: 12, height: 12 },
      data: { edgeType },
    });
  }

  return { nodes, edges, name: jsonData.name || '', variables: jsonData.variables || {} };
}

/**
 * 将 React Flow 的 nodes + edges 导出为 Workflow JSON。
 * @param {Object[]} nodes
 * @param {Object[]} edges
 * @param {string} name
 * @param {Object} variables
 * @returns {Object}
 */
export function flowToJson(nodes, edges, name = '', variables = {}) {
  const jsonNodes = nodes.map((node) => {
    const entry = {
      id: parseInt(node.id, 10),
      type: node.data.nodeType,
      x: Math.round(node.position.x),
      y: Math.round(node.position.y),
    };
    if (node.data.name) {
      entry.name = node.data.name;
    }
    if (node.data.config && Object.keys(node.data.config).length > 0) {
      entry.config = { ...node.data.config };
    }
    return entry;
  });

  const jsonEdges = edges.map((edge) => {
    const result = {
      from: parseInt(edge.source, 10),
      to: parseInt(edge.target, 10),
    };
    const edgeType = edge.data?.edgeType;
    if (edgeType && edgeType !== 0) {
      result.type = edgeType;
    }
    return result;
  });

  const result = { name };
  if (variables && Object.keys(variables).length > 0) {
    result.variables = variables;
  }
  result.nodes = jsonNodes;
  result.edges = jsonEdges;
  return result;
}

/**
 * 导出为 JSON 字符串。
 */
export function exportToJsonString(nodes, edges, name, variables = {}) {
  const json = flowToJson(nodes, edges, name, variables);
  return JSON.stringify(json, null, 2);
}

/**
 * 触发 JSON 文件下载。
 */
export function downloadJson(nodes, edges, name, variables = {}) {
  const text = exportToJsonString(nodes, edges, name, variables);
  const blob = new Blob([text], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${name || 'workflow'}.json`;
  a.click();
  URL.revokeObjectURL(url);
}
