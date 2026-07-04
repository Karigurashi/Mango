import { useReducer, useCallback } from 'react';

// ---- Action Types ----
const ADD_USER_MSG = 'ADD_USER_MSG';
const START_TURN = 'START_TURN';
const DELTA_THINKING = 'DELTA_THINKING';
const DELTA_TEXT = 'DELTA_TEXT';
const COMPLETE_TEXT = 'COMPLETE_TEXT';
const START_TOOL = 'START_TOOL';
const TOOL_RESULT = 'TOOL_RESULT';
const STATE_CHANGE = 'STATE_CHANGE';
const COMPACTION = 'COMPACTION';
const USAGE = 'USAGE';
const ERROR = 'ERROR';
const DONE = 'DONE';
const RESET = 'RESET';
const MODEL_SWITCHED = 'MODEL_SWITCHED';
const CLEARED = 'CLEARED';
const BACKEND_STATUS = 'BACKEND_STATUS';

let nextId = 1;
function genId() { return nextId++; }

const initialState = {
  messages: [],
  streamingMsg: null,
  status: 'idle',        // 'idle' | 'streaming' | 'error'
  modelName: '',
  backendStatus: 'disconnected', // 'connected' | 'disconnected' | 'dead'
};

function chatReducer(state, action) {
  switch (action.type) {
    case ADD_USER_MSG:
      return {
        ...state,
        messages: [...state.messages, {
          id: genId(),
          role: 'user',
          content: action.content,
          timestamp: Date.now(),
        }],
        streamingMsg: {
id: genId(),
          role: 'assistant',
          content: '',
          reasoningContent: '',
          toolCalls: [],
          turn: 0,
          promptTokens: 0,
          completionTokens: 0,
          cacheHitRate: 0,
        },
        status: 'streaming',
      };

    case START_TURN:
      return state.streamingMsg
        ? { ...state, streamingMsg: { ...state.streamingMsg, turn: action.turn } }
        : state;

    case DELTA_THINKING:
      return state.streamingMsg
        ? {
            ...state,
            streamingMsg: {
              ...state.streamingMsg,
              reasoningContent: state.streamingMsg.reasoningContent + (action.text || ''),
            },
          }
        : state;

    case DELTA_TEXT:
      return state.streamingMsg
        ? {
            ...state,
            streamingMsg: {
              ...state.streamingMsg,
              content: state.streamingMsg.content + (action.text || ''),
            },
          }
        : state;

    case COMPLETE_TEXT:
      return state.streamingMsg
        ? {
            ...state,
            streamingMsg: {
              ...state.streamingMsg,
              content: action.text || state.streamingMsg.content,
            },
          }
        : state;

    case START_TOOL:
      return state.streamingMsg
        ? {
            ...state,
            streamingMsg: {
              ...state.streamingMsg,
              toolCalls: [
                ...state.streamingMsg.toolCalls,
                {
                  id: genId(),
                  name: action.toolName,
                  args: action.args || {},
                  result: null,
                  success: null,
                  status: 'running',
                },
              ],
            },
          }
        : state;

    case TOOL_RESULT:
      if (!state.streamingMsg) return state;
      const toolCalls = state.streamingMsg.toolCalls.map((tc) =>
        tc.name === action.toolName && tc.status === 'running'
          ? { ...tc, result: action.content || '', success: action.success, status: 'done' }
          : tc
      );
      return { ...state, streamingMsg: { ...state.streamingMsg, toolCalls } };

    case STATE_CHANGE:
      return state;

    case COMPACTION:
      return state;

    case USAGE:
      return state.streamingMsg
        ? {
            ...state,
            streamingMsg: {
              ...state.streamingMsg,
              promptTokens: (state.streamingMsg.promptTokens || 0) + (action.promptTokens || 0),
              completionTokens: (state.streamingMsg.completionTokens || 0) + (action.completionTokens || 0),
              cacheHitRate: action.cacheHitRate || 0,
            },
          }
        : state;

    case ERROR:
      const errMsg = {
        id: genId(),
        role: 'error',
        content: action.msg || 'Unknown error',
        timestamp: Date.now(),
      };
      return {
        ...state,
        messages: state.streamingMsg
          ? [...state.messages, { ...state.streamingMsg, content: state.streamingMsg.content || '(interrupted)' }, errMsg]
          : [...state.messages, errMsg],
        streamingMsg: null,
        status: 'error',
      };

    case DONE:
      return {
        ...state,
        messages: state.streamingMsg
          ? [...state.messages, { ...state.streamingMsg }]
          : state.messages,
        streamingMsg: null,
        status: 'idle',
      };

    case RESET:
      return { ...initialState, backendStatus: state.backendStatus, modelName: state.modelName };

    case MODEL_SWITCHED:
      return { ...state, modelName: action.model || action.fullName || '' };

    case CLEARED:
      return { ...state, messages: [], streamingMsg: null, status: 'idle' };

    case BACKEND_STATUS:
      return { ...state, backendStatus: action.status };

    default:
      return state;
  }
}

export default function useChatStore() {
  const [state, dispatch] = useReducer(chatReducer, initialState);

  const addUserMsg = useCallback((content) => dispatch({ type: ADD_USER_MSG, content }), []);
  const startTurn = useCallback((turn) => dispatch({ type: START_TURN, turn }), []);
  const deltaThinking = useCallback((text) => dispatch({ type: DELTA_THINKING, text }), []);
  const deltaText = useCallback((text) => dispatch({ type: DELTA_TEXT, text }), []);
  const completeText = useCallback((text) => dispatch({ type: COMPLETE_TEXT, text }), []);
  const startTool = useCallback((toolName, args) => dispatch({ type: START_TOOL, toolName, args }), []);
  const toolResult = useCallback((toolName, content, success) => dispatch({ type: TOOL_RESULT, toolName, content, success }), []);
  const stateChange = useCallback((st) => dispatch({ type: STATE_CHANGE, state: st }), []);
  const compaction = useCallback((tokenSaved, compactedCount, content) => dispatch({ type: COMPACTION, tokenSaved, compactedCount, content }), []);
  const usage = useCallback((promptTokens, completionTokens, cacheHitRate) => dispatch({ type: USAGE, promptTokens, completionTokens, cacheHitRate }), []);
  const error = useCallback((msg) => dispatch({ type: ERROR, msg }), []);
  const done = useCallback(() => dispatch({ type: DONE }), []);
  const reset = useCallback(() => dispatch({ type: RESET }), []);
  const modelSwitched = useCallback((model, fullName) => dispatch({ type: MODEL_SWITCHED, model, fullName }), []);
  const cleared = useCallback(() => dispatch({ type: CLEARED }), []);
  const backendStatus = useCallback((status) => dispatch({ type: BACKEND_STATUS, status }), []);

  return {
    ...state,
    addUserMsg,
    startTurn,
    deltaThinking,
    deltaText,
    completeText,
    startTool,
    toolResult,
    stateChange,
    compaction,
    usage,
    error,
    done,
    reset,
    modelSwitched,
    cleared,
    backendStatus,
  };
}
