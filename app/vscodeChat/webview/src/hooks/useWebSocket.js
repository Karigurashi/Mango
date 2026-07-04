import { useEffect, useRef, useCallback } from 'react';

/**
 * WebSocket 连接 Hook。
 *
 * 连接 wsUrl → 按 \n 拆包处理 JSON Lines 协议 → 分发到 store actions。
 * 支持自动重连（指数退避），仅处理流式通道，不涉及 VSCode postMessage。
 *
 * @param {string} wsUrl - WebSocket 连接 URL
 * @param {object} actions - 从 useChatStore 解构的 dispatch 函数集合
 * @param {object} actions.addUserMsg
 * @param {object} actions.startTurn
 * @param {object} actions.deltaThinking
 * @param {object} actions.deltaText
 * @param {object} actions.completeText
 * @param {object} actions.startTool
 * @param {object} actions.toolResult
 * @param {object} actions.compaction
 * @param {object} actions.usage
 * @param {object} actions.error
 * @param {object} actions.done
 * @param {object} actions.modelSwitched
 * @param {object} actions.cleared
 * @param {object} actions.backendStatus
 */
export default function useWebSocket(wsUrl, actions) {
  const wsRef = useRef(null);
  const reconnectTimerRef = useRef(null);
  const reconnectDelayRef = useRef(1000);
  const bufferRef = useRef('');
  const mountedRef = useRef(true);

  const connect = useCallback(() => {
    if (!wsUrl || !mountedRef.current) return;

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        reconnectDelayRef.current = 1000;
        actions.backendStatus?.('connected');
      };

      ws.onmessage = (event) => {
        // 粘包处理：追加 buffer，按 \n 拆包
        bufferRef.current += event.data;
        const lines = bufferRef.current.split('\n');
        bufferRef.current = lines.pop() || ''; // 残留放回 buffer

        for (const line of lines) {
          if (!line.trim()) continue;
          try {
            const msg = JSON.parse(line);
            dispatchEvent(msg, actions);
          } catch (e) {
            // 忽略解析错误
          }
        }
      };

      ws.onclose = () => {
        wsRef.current = null;
        actions.backendStatus?.('disconnected');
        scheduleReconnect();
      };

      ws.onerror = () => {
        wsRef.current?.close();
      };
    } catch (e) {
      scheduleReconnect();
    }
  }, [wsUrl, actions]);

  const scheduleReconnect = useCallback(() => {
    if (!mountedRef.current) return;
    const delay = reconnectDelayRef.current;
    reconnectDelayRef.current = Math.min(delay * 2, 5000);
    reconnectTimerRef.current = setTimeout(connect, delay);
  }, [connect]);

  const send = useCallback((msg) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    connect();
    return () => {
      mountedRef.current = false;
      clearTimeout(reconnectTimerRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { send };
}

// ---- 事件分发 ----

function dispatchEvent(msg, actions) {
  const type = msg.type;
  switch (type) {
    case 'turn_start':
      actions.startTurn?.(msg.turn);
      break;
    case 'thinking_delta':
      actions.deltaThinking?.(msg.text);
      break;
    case 'thinking_complete':
      // 思考完成，无需额外动作
      break;
    case 'text_delta':
      actions.deltaText?.(msg.text);
      break;
    case 'text_complete':
      actions.completeText?.(msg.text);
      break;
    case 'tool_start':
      actions.startTool?.(msg.toolName, msg.args);
      break;
    case 'tool_result':
      actions.toolResult?.(msg.toolName, msg.content, msg.success);
      break;
    case 'state_change':
      break;
    case 'compaction':
      actions.compaction?.(msg.tokenSaved, msg.compactedCount, msg.content);
      break;
    case 'usage':
      actions.usage?.(msg.promptTokens, msg.completionTokens, msg.cacheHitRate);
      break;
    case 'done':
      actions.done?.();
      if (msg.promptTokens || msg.completionTokens) {
        actions.usage?.(msg.promptTokens || 0, msg.completionTokens || 0, msg.cacheHitRate || 0);
      }
      break;
    case 'error':
      actions.error?.(msg.msg);
      break;
    case 'model_switched':
      actions.modelSwitched?.(msg.model, msg.fullName);
      break;
    case 'cleared':
      actions.cleared?.();
      break;
    case 'backendStatus':
      actions.backendStatus?.(msg.status);
      break;
    default:
      break;
  }
}
