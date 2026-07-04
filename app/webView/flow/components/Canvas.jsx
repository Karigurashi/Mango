import { useCallback, useRef, useState, useMemo, memo } from 'react';
import {
  ReactFlow,
  Controls,
  Background,
  MiniMap,
  BackgroundVariant,
  addEdge,
  applyNodeChanges,
  applyEdgeChanges,
  MarkerType,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import WorkflowNode from '../nodes/WorkflowNode';
import { getNodeDef, CATEGORY_LABEL_COLORS } from '../nodes/nodeRegistry';
import { generateNodeId } from '../utils/workflowIO';

const nodeTypes = { workflowNode: WorkflowNode };

/** 前端 EExecutionStatus 枚举，与后端 eExecutionStatus.py 保持一致 */
export const EExecutionStatus = {
  RUNNING: 'running',
  COMPLETED: 'completed',
  FAILED: 'failed',
  CANCELLED: 'cancelled',
};

/** 连线验证 */
function isValidConnection(connection, nodes) {
  const { source, target } = connection;
  if (source === target) return false;
  return nodes.some((n) => n.id === source) && nodes.some((n) => n.id === target);
}

/** OUT=蓝，SUB_NODE=紫 */
const EDGE_COLORS = { out: '#5e9cf5', sub: '#c98bdb' };

/** 默认边样式（不参与 useMemo，静态引用避免浅比较失效） */
const defaultEdgeOptions = {
  type: 'default',
  style: { stroke: EDGE_COLORS.out, strokeWidth: 1.5 },
  markerEnd: { type: MarkerType.ArrowClosed, color: EDGE_COLORS.out, width: 12, height: 12 },
};

const Canvas = memo(function Canvas({ nodes, setNodes, edges, setEdges, onSelectNode, nodeStatuses }) {
  const reactFlowWrapper = useRef(null);
  const [reactFlowInstance, setReactFlowInstance] = useState(null);

  const onConnect = useCallback(
    (params) => {
      const isSubNode = params.sourceHandle === 'source-sub';
      const edgeType = isSubNode ? 1 : 0;
      const stroke = isSubNode ? EDGE_COLORS.sub : EDGE_COLORS.out;

      setEdges((eds) =>
        addEdge(
          {
            ...params,
            type: 'default',
            style: { stroke, strokeWidth: 1.5 },
            markerEnd: { type: MarkerType.ArrowClosed, color: stroke, width: 12, height: 12 },
            data: { edgeType },
          },
          eds
        )
      );
    },
    [setEdges]
  );

  const onDragOver = useCallback((event) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  const onDrop = useCallback(
    (event) => {
      event.preventDefault();
      const nodeType = event.dataTransfer.getData('application/workflow-node-type');
      if (!nodeType || !reactFlowInstance) return;

      const def = getNodeDef(nodeType);
      if (!def) return;

      const position = reactFlowInstance.screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      });

      const newId = generateNodeId();
      const newNode = {
        id: String(newId),
        type: 'workflowNode',
        position,
        data: { nodeType, config: {} },
      };

      setNodes((nds) => nds.concat(newNode));
    },
    [reactFlowInstance, setNodes]
  );

  const isValidConnectionCb = useMemo(
    () => (conn) => isValidConnection(conn, nodes),
    [nodes]
  );

  const onNodeClick = useCallback(
    (event, node) => { onSelectNode(node); },
    [onSelectNode]
  );

  const onNodesChange = useCallback(
    (changes) => setNodes((nds) => applyNodeChanges(changes, nds)),
    [setNodes]
  );

  const onEdgesChange = useCallback(
    (changes) => setEdges((eds) => applyEdgeChanges(changes, eds)),
    [setEdges]
  );

  const onPaneClick = useCallback(() => {
    onSelectNode(null);
  }, [onSelectNode]);

  // 根据节点执行状态给边加 className。用 ref 缓存上次结果，状态未变时跳过重建。
  const prevStatusRef = useRef(null);
  const cachedEdgesRef = useRef(null);

  const edgesWithStatus = useMemo(() => {
    if (!nodeStatuses || Object.keys(nodeStatuses).length === 0) {
      prevStatusRef.current = null;
      cachedEdgesRef.current = null;
      return edges;
    }

    // 快速差分：与上次状态完全一致则复用缓存
    if (prevStatusRef.current) {
      const prev = prevStatusRef.current;
      const keys = Object.keys(nodeStatuses);
      if (keys.length === Object.keys(prev).length &&
          keys.every((k) => nodeStatuses[k] === prev[k])) {
        return cachedEdgesRef.current || edges;
      }
    }

    prevStatusRef.current = { ...nodeStatuses };

    const result = edges.map((e) => {
      const sourceStatus = nodeStatuses[e.source];
      const targetStatus = nodeStatuses[e.target];

      if (sourceStatus === EExecutionStatus.RUNNING || targetStatus === EExecutionStatus.RUNNING) {
        return { ...e, animated: true, className: 'edge-running' };
      }
      if (targetStatus === EExecutionStatus.COMPLETED) {
        return { ...e, animated: false, className: 'edge-completed' };
      }
      if (targetStatus === EExecutionStatus.FAILED) {
        return { ...e, animated: false, className: 'edge-failed' };
      }
      if (targetStatus === EExecutionStatus.CANCELLED) {
        return { ...e, animated: false, className: 'edge-cancelled' };
      }
      return { ...e, animated: false, className: undefined };
    });

    cachedEdgesRef.current = result;
    return result;
  }, [edges, nodeStatuses]);

  // 将 nodeStatuses 注入节点 data.__status，同样用 ref 差分
  const prevNodeStatusRef = useRef(null);
  const cachedNodesRef = useRef(null);

  const nodesWithStatus = useMemo(() => {
    if (!nodeStatuses || Object.keys(nodeStatuses).length === 0) {
      prevNodeStatusRef.current = null;
      cachedNodesRef.current = null;
      return nodes;
    }

    if (prevNodeStatusRef.current) {
      const prev = prevNodeStatusRef.current;
      const keys = Object.keys(nodeStatuses);
      if (keys.length === Object.keys(prev).length &&
          keys.every((k) => nodeStatuses[k] === prev[k])) {
        return cachedNodesRef.current || nodes;
      }
    }

    prevNodeStatusRef.current = { ...nodeStatuses };

    const result = nodes.map((n) => {
      const status = nodeStatuses[n.id];
      if (!status) return n;
      return { ...n, data: { ...n.data, __status: status } };
    });

    cachedNodesRef.current = result;
    return result;
  }, [nodes, nodeStatuses]);

  return (
    <div ref={reactFlowWrapper} style={{ flex: 1, height: '100%' }}>
      <ReactFlow
        nodes={nodesWithStatus}
        edges={edgesWithStatus}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        isValidConnection={isValidConnectionCb}
        nodeTypes={nodeTypes}
        onInit={setReactFlowInstance}
        onDrop={onDrop}
        onDragOver={onDragOver}
        onNodeClick={onNodeClick}
        onPaneClick={onPaneClick}
        fitView
        deleteKeyCode={['Delete', 'Backspace']}
        multiSelectionKeyCode="Shift"
        selectNodesOnDrag={false}
        elevateNodesOnSelect={false}
        defaultEdgeOptions={defaultEdgeOptions}
        style={{ background: '#0d1117' }}
      >
        <Controls
          style={{
            background: '#191e28',
            border: '1px solid #252b36',
            borderRadius: 8,
            overflow: 'hidden',
          }}
        />
        <Background
          variant={BackgroundVariant.Lines}
          gap={20}
          size={0.6}
          color="#1a2230"
        />
        <MiniMap
          style={{
            background: '#12161e',
            border: '1px solid #252b36',
            borderRadius: 8,
            overflow: 'hidden',
          }}
          nodeColor={(node) => {
            const def = getNodeDef(node.data?.nodeType);
            if (!def) return '#252b36';
            return CATEGORY_LABEL_COLORS[def.category] || '#252b36';
          }}
          maskColor="rgba(0,0,0,0.75)"
          pannable
          zoomable
        />
      </ReactFlow>
    </div>
  );
});

export default Canvas;
