import { useState, useCallback, useEffect, useRef } from 'react';
import { ReactFlowProvider } from '@xyflow/react';
import Canvas from './components/Canvas';
import NodePalette from './components/NodePalette';
import RightPanel from './components/RightPanel';
import Toolbar from './components/Toolbar';
import { initNodeRegistry, isReady } from './nodes/nodeRegistry';
import { jsonToFlow } from './utils/workflowIO';
import defaultWorkflowJson from '../config/Workflow.json';

const defaultWorkflow = jsonToFlow(defaultWorkflowJson);

export default function App() {
  const [nodes, setNodes] = useState(defaultWorkflow.nodes);
  const [edges, setEdges] = useState(defaultWorkflow.edges);
  const [name, setName] = useState(defaultWorkflow.name);
  const [variables, setVariables] = useState(defaultWorkflow.variables);
  const [selectedNode, setSelectedNode] = useState(null);
  const [ready, setReady] = useState(isReady());

  // 侧边栏状态
  const [leftCollapsed, setLeftCollapsed] = useState(false);
  const [rightCollapsed, setRightCollapsed] = useState(false);
  const [rightWidth, setRightWidth] = useState(340);

  // 节点执行状态（运行时可视化）
  const [nodeStatuses, setNodeStatuses] = useState({});

  // 拖拽 resize 状态
  const resizingRef = useRef(false);
  const startXRef = useRef(0);
  const startWidthRef = useRef(340);

  useEffect(() => {
    let cancelled = false;
    let retries = 0;
    const maxRetries = 5;
    const retryDelay = 1000; // ms

    const tryInit = async () => {
      while (retries < maxRetries) {
        try {
          await initNodeRegistry();
          if (!cancelled) setReady(true);
          return;
        } catch (err) {
          retries++;
          if (retries >= maxRetries) {
            console.error('节点注册表加载失败（已达最大重试次数）:', err);
            if (!cancelled) setReady(true); // 即使失败也进入界面，用空注册表
            return;
          }
          console.warn(`节点注册表加载失败，${retryDelay / 1000}s 后重试 (${retries}/${maxRetries})...`, err);
          await new Promise((r) => setTimeout(r, retryDelay));
        }
      }
    };

    tryInit();
    return () => { cancelled = true; };
  }, []);

  // 右面板拖拽 resize 逻辑
  useEffect(() => {
    const onMouseMove = (e) => {
      if (!resizingRef.current) return;
      const delta = startXRef.current - e.clientX;
      const newWidth = Math.min(600, Math.max(260, startWidthRef.current + delta));
      setRightWidth(newWidth);
    };
    const onMouseUp = () => {
      if (resizingRef.current) {
        resizingRef.current = false;
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
      }
    };
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
    return () => {
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
    };
  }, []);

  const handleResizeStart = useCallback((e) => {
    resizingRef.current = true;
    startXRef.current = e.clientX;
    startWidthRef.current = rightWidth;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }, [rightWidth]);

  const handleSelectNode = useCallback((node) => {
    setSelectedNode(node);
  }, []);

  if (!ready) {
    return (
      <div style={{
        width: '100vw', height: '100vh', display: 'flex',
        alignItems: 'center', justifyContent: 'center',
        background: '#0a0e14', color: '#5a606b',
        fontSize: 13,
      }}>
        正在加载节点注册表…
      </div>
    );
  }

  return (
    <ReactFlowProvider>
      <div style={styles.root}>
        <Toolbar
          nodes={nodes}
          edges={edges}
          name={name}
          setNodes={setNodes}
          setEdges={setEdges}
          setName={setName}
          variables={variables}
          setVariables={setVariables}
        />
        <div style={styles.body}>
          <NodePalette
            collapsed={leftCollapsed}
            onToggleCollapse={() => setLeftCollapsed((v) => !v)}
          />
          <Canvas
            nodes={nodes}
            setNodes={setNodes}
            edges={edges}
            setEdges={setEdges}
            onSelectNode={handleSelectNode}
            nodeStatuses={nodeStatuses}
          />

          {/* 拖拽分隔条 */}
          {!rightCollapsed && (
            <div
              className="resize-handle-global"
              style={styles.resizeHandle}
              onMouseDown={handleResizeStart}
            />
          )}

          <RightPanel
            selectedNode={selectedNode}
            nodes={nodes}
            setNodes={setNodes}
            edges={edges}
            name={name}
            variables={variables}
            panelWidth={rightWidth}
            collapsed={rightCollapsed}
            onToggleCollapse={() => setRightCollapsed((v) => !v)}
            setNodeStatuses={setNodeStatuses}
          />
        </div>
      </div>
    </ReactFlowProvider>
  );
}

const styles = {
  root: {
    width: '100vw',
    height: '100vh',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    background: '#0a0e14',
  },
  body: {
    flex: 1,
    display: 'flex',
    overflow: 'hidden',
  },
  resizeHandle: {
    width: 3,
    cursor: 'col-resize',
    background: 'transparent',
    transition: 'background 0.15s',
    flexShrink: 0,
    zIndex: 10,
  },
};
