/** extension.js —— Qoder Chat VSCode 扩展入口。

架构：
  Python agentServer.py (child_process)
    ↕ stdin/stdout 字节透传（零 JSON 解析）
  TCP Server (127.0.0.1:随机端口)
    ↕ 字节透传
  WebView WebSocket 直连

Extension 层仅做 Buffer 字节拷贝，不参与 JSON 序列化/解析。
*/

const vscode = require('vscode');
const { spawn } = require('child_process');
const net = require('net');
const path = require('path');
const fs = require('fs');

// ---- 全局状态 ----
let pythonProcess = null;
let tcpServer = null;
let mcpTcpServer = null;   // MCP 桥接 TCP Server
let wsClient = null;       // 当前连接的 WebSocket 客户端
let mcpPort = 0;           // MCP 桥接端口
let restartCount = 0;
const MAX_RESTART = 3;
const RESTART_DELAY = 2000; // ms

// ---- 激活 ----

/**
 * @param {vscode.ExtensionContext} context
 */
function activate(context) {
    const extensionPath = context.extensionPath;
    const projectRoot = path.resolve(extensionPath, '..', '..');

    // 1. 启动 MCP 桥接 TCP Server（先启动以确定端口）
    mcpTcpServer = net.createServer((socket) => {
        socket.setNoDelay(true);
        let buffer = '';
        socket.on('data', (buf) => {
            buffer += buf.toString('utf-8');
            // JSON-RPC 按行分隔
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';
            for (const line of lines) {
                if (!line.trim()) continue;
                handleMCPRequest(socket, line.trim());
            }
        });
        socket.on('error', () => {});
    });

    mcpTcpServer.listen(0, '127.0.0.1', () => {
        mcpPort = mcpTcpServer.address().port;
        console.log(`[QoderChat] MCP TCP server on 127.0.0.1:${mcpPort}`);

        // 2. 启动 WebSocket TCP Server
        tcpServer = net.createServer((socket) => {
            // 仅允许单客户端
            if (wsClient && !wsClient.destroyed) {
                wsClient.destroy();
            }
            wsClient = socket;
            socket.setNoDelay(true);

            // Python stdout → WebSocket（透传，零解析）
            if (pythonProcess && pythonProcess.stdout) {
                pythonProcess.stdout.on('data', (buf) => {
                    if (wsClient && !wsClient.destroyed) {
                        wsClient.write(buf);
                    }
                });
            }

            // WebSocket → Python stdin（透传，零解析）
            socket.on('data', (buf) => {
                if (pythonProcess && pythonProcess.stdin && pythonProcess.stdin.writable) {
                    pythonProcess.stdin.write(buf);
                }
            });

            socket.on('close', () => {
                wsClient = null;
            });

            socket.on('error', () => {
                wsClient = null;
            });
        });

        tcpServer.listen(0, '127.0.0.1', () => {
            const port = tcpServer.address().port;
            console.log(`[QoderChat] WS TCP server on 127.0.0.1:${port}`);

            // 3. 启动 Python Agent 进程
            spawnPython(extensionPath, projectRoot);

            // 4. 注册 WebView Provider（注入端口号）
            context.subscriptions.push(
                vscode.window.registerWebviewViewProvider('qoderChatView',
                    new ChatViewProvider(context.extensionUri, port))
            );
        });
    });

    // 4. 注册命令
    context.subscriptions.push(
        vscode.commands.registerCommand('qoder-chat.open', () => {
            vscode.commands.executeCommand('qoderChatView.focus');
        })
    );
    context.subscriptions.push(
        vscode.commands.registerCommand('qoder-chat.focusInput', () => {
            // 通过 postMessage 通知 WebView 聚焦输入框
            ChatViewProvider._currentInstance?._postToWebview({ type: 'focusInput' });
        })
    );

    console.log('[QoderChat] Extension activated');
}

// ---- 反激活 ----

function deactivate() {
    if (wsClient && !wsClient.destroyed) {
        wsClient.destroy();
        wsClient = null;
    }
    if (tcpServer) {
        tcpServer.close();
        tcpServer = null;
    }
    if (mcpTcpServer) {
        mcpTcpServer.close();
        mcpTcpServer = null;
    }
    if (pythonProcess) {
        pythonProcess.kill();
        pythonProcess = null;
    }
    console.log('[QoderChat] Extension deactivated');
}

// ---- Python 进程管理 ----

/**
 * @param {string} extensionPath
 * @param {string} projectRoot
 */
function spawnPython(extensionPath, projectRoot) {
    const serverScript = path.join(extensionPath, 'server', 'agentServer.py');

    // 生成 .mcp.json 到 workspace 目录
    writeMCPJson(extensionPath, projectRoot);

    console.log(`[QoderChat] Spawning: python ${serverScript}`);

    pythonProcess = spawn('python', [serverScript], {
        cwd: projectRoot,
        stdio: ['pipe', 'pipe', 'pipe'],
        env: {
            ...process.env,
            PYTHONUNBUFFERED: '1',
            QODER_MCP_PORT: String(mcpPort), // MCP 桥接端口
        },
    });

    // stderr → VSCode 输出通道（仅日志）
    pythonProcess.stderr.on('data', (data) => {
        console.log(`[agentServer] ${data.toString().trim()}`);
    });

    pythonProcess.on('error', (err) => {
        console.error(`[QoderChat] Python process error: ${err.message}`);
    });

    pythonProcess.on('exit', (code, signal) => {
        console.log(`[QoderChat] Python process exited: code=${code} signal=${signal}`);

        // 通知 WebView 进程已断开
        ChatViewProvider._currentInstance?._postToWebview({
            type: 'backendStatus',
            status: 'disconnected',
            code: code,
            signal: signal,
        });

        // 自动重启（限次）
        if (restartCount < MAX_RESTART) {
            restartCount++;
            console.log(`[QoderChat] Auto-restart ${restartCount}/${MAX_RESTART} in ${RESTART_DELAY}ms...`);
            setTimeout(() => spawnPython(extensionPath, projectRoot), RESTART_DELAY);
        } else {
            ChatViewProvider._currentInstance?._postToWebview({
                type: 'backendStatus',
                status: 'dead',
                msg: `Process exited after ${MAX_RESTART} restart attempts`,
            });
        }
    });

    // 进程启动通知 WebView
    pythonProcess.on('spawn', () => {
        restartCount = 0; // 成功后重置计数
        ChatViewProvider._currentInstance?._postToWebview({
            type: 'backendStatus',
            status: 'connected',
        });
    });
}

// ---- WebView Provider ----

class ChatViewProvider {
    /** @type {ChatViewProvider|null} */
    static _currentInstance = null;

    /**
     * @param {vscode.Uri} extensionUri
     * @param {number} wsPort
     */
    constructor(extensionUri, wsPort) {
        this._extensionUri = extensionUri;
        this._wsPort = wsPort;
        /** @type {vscode.WebviewView|null} */
        this._view = null;
        ChatViewProvider._currentInstance = this;
    }

    /**
     * @param {vscode.WebviewView} webviewView
     * @param {vscode.WebviewViewResolveContext} _context
     * @param {vscode.CancellationToken} _token
     */
    resolveWebviewView(webviewView, _context, _token) {
        this._view = webviewView;

        webviewView.webview.options = {
            enableScripts: true,
            localResourceRoots: [this._extensionUri],
        };

        // 生成 WebView HTML，注入 WebSocket URL
        webviewView.webview.html = this._getHtml();

        // 处理来自 WebView 的 postMessage（VSCode API 操作）
        webviewView.webview.onDidReceiveMessage((msg) => {
            this._handleWebviewMessage(msg);
        });

        webviewView.onDidDispose(() => {
            this._view = null;
            ChatViewProvider._currentInstance = null;
        });
    }

    /**
     * @param {object} msg
     */
    _postToWebview(msg) {
        if (this._view) {
            this._view.webview.postMessage(msg);
        }
    }

    /**
     * @param {object} msg
     */
    _handleWebviewMessage(msg) {
        // 预留：处理需要 VSCode API 的操作（文件读写、诊断等）
        switch (msg.type) {
            case 'getModels':
                // 返回可用模型列表（从配置读取）
                this._postToWebview({
                    type: 'models',
                    models: ['deepseek-high', 'deepseek-chat', 'gemini-flash', 'claude-sonnet'],
                    defaultModel: 'deepseek-high',
                });
                break;

            case 'getWorkspaceInfo':
                const folders = vscode.workspace.workspaceFolders;
                this._postToWebview({
                    type: 'workspaceInfo',
                    root: folders ? folders[0].uri.fsPath : '',
                });
                break;

            default:
                break;
        }
    }

    /**
     * @returns {string}
     */
    _getHtml() {
        const wsUrl = `ws://127.0.0.1:${this._wsPort}`;
        return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Qoder Chat</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        html, body, #root {
            width: 100%; height: 100%; overflow: hidden;
            background: #0d1117;
            font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif;
            font-size: 13px; color: #c9cdd4;
        }
        #loading {
            display: flex; align-items: center; justify-content: center;
            height: 100%; color: #5a606b; font-size: 13px;
        }
    </style>
</head>
<body>
    <div id="root">
        <div id="loading">Connecting to agent...</div>
    </div>
    <script>
        window.__WS_URL__ = '${wsUrl}';
        window.__VSCODE_API__ = acquireVsCodeApi();
    </script>
    <script type="module" src="/src/main.jsx"></script>
</body>
</html>`;
    }
}

// ---- MCP 请求处理 ----

/**
 * 处理来自 MCP 桥接的 JSON-RPC 请求，执行 VSCode API 操作
 * @param {net.Socket} socket
 * @param {string} rawLine
 */
async function handleMCPRequest(socket, rawLine) {
    let request;
    try {
        request = JSON.parse(rawLine);
    } catch {
        return;
    }

    const { id, method, params } = request;
    if (!method || id === undefined) return;

    try {
        let result;
        switch (method) {
            // ---- tools/list ----
            case 'tools/list':
                result = await listMCPTools();
                break;

            // ---- tools/call ----
            case 'tools/call':
                result = await callMCPTool(params);
                break;

            // ---- initialize ----
            case 'initialize':
                result = {
                    protocolVersion: '2024-11-05',
                    capabilities: {},
                    serverInfo: { name: 'vscode-mcp-bridge', version: '1.0.0' },
                };
                break;

            default:
                result = `Unknown method: ${method}`;
        }
        socket.write(JSON.stringify({ jsonrpc: '2.0', id, result }) + '\n');
    } catch (err) {
        socket.write(JSON.stringify({
            jsonrpc: '2.0',
            id,
            error: { code: -32603, message: err.message },
        }) + '\n');
    }
}

/**
 * 列出所有可用的 VSCode MCP 工具
 */
async function listMCPTools() {
    return {
        tools: [
            { name: 'vscode.read_file', description: 'Read file content from workspace', inputSchema: { type: 'object', properties: { path: { type: 'string', description: 'Absolute or relative file path' } }, required: ['path'] } },
            { name: 'vscode.write_file', description: 'Create or overwrite a file', inputSchema: { type: 'object', properties: { path: { type: 'string', description: 'File path to write' }, content: { type: 'string', description: 'Content to write' } }, required: ['path', 'content'] } },
            { name: 'vscode.edit_file', description: 'Replace text in file via search/replace', inputSchema: { type: 'object', properties: { path: { type: 'string', description: 'File path' }, oldText: { type: 'string', description: 'Text to find and replace' }, newText: { type: 'string', description: 'Replacement text' } }, required: ['path', 'oldText', 'newText'] } },
            { name: 'vscode.list_directory', description: 'List directory contents', inputSchema: { type: 'object', properties: { path: { type: 'string', description: 'Directory path' } }, required: ['path'] } },
            { name: 'vscode.search_codebase', description: 'Search text/regex in workspace files', inputSchema: { type: 'object', properties: { pattern: { type: 'string', description: 'Search pattern (text or regex)' }, fileTypes: { type: 'string', description: 'Optional comma-separated file extensions' } }, required: ['pattern'] } },
            { name: 'vscode.execute_command', description: 'Run terminal command in workspace', inputSchema: { type: 'object', properties: { command: { type: 'string', description: 'Shell command to execute' }, timeout: { type: 'number', description: 'Timeout in seconds (default: 30)' } }, required: ['command'] } },
            { name: 'vscode.get_diagnostics', description: 'Get diagnostics (errors/warnings) for files', inputSchema: { type: 'object', properties: { path: { type: 'string', description: 'Optional file path; omit for all files' } } } },
            { name: 'vscode.open_file', description: 'Open file in editor with optional line number', inputSchema: { type: 'object', properties: { path: { type: 'string', description: 'File path to open' }, line: { type: 'number', description: 'Optional line number (1-based)' } }, required: ['path'] } },
        ],
    };
}

/**
 * 执行 VSCode MCP 工具调用
 */
async function callMCPTool(params) {
    const toolName = params?.name;
    const args = params?.arguments || {};

    switch (toolName) {
        case 'vscode.read_file':
            return await vscodeReadFile(args.path);
        case 'vscode.write_file':
            return await vscodeWriteFile(args.path, args.content);
        case 'vscode.edit_file':
            return await vscodeEditFile(args.path, args.oldText, args.newText);
        case 'vscode.list_directory':
            return await vscodeListDirectory(args.path);
        case 'vscode.search_codebase':
            return await vscodeSearchCodebase(args.pattern, args.fileTypes);
        case 'vscode.execute_command':
            return await vscodeExecuteCommand(args.command, args.timeout);
        case 'vscode.get_diagnostics':
            return await vscodeGetDiagnostics(args.path);
        case 'vscode.open_file':
            return await vscodeOpenFile(args.path, args.line);
        default:
            return `Unknown tool: ${toolName}`;
    }
}

// ---- VSCode 工具实现 ----

function resolvePath(inputPath) {
    if (!inputPath) return '';
    if (path.isAbsolute(inputPath)) return inputPath;
    const folders = vscode.workspace.workspaceFolders;
    const root = folders ? folders[0].uri.fsPath : process.cwd();
    return path.resolve(root, inputPath);
}

async function vscodeReadFile(filePath) {
    const resolved = resolvePath(filePath);
    const uri = vscode.Uri.file(resolved);
    const content = await vscode.workspace.fs.readFile(uri);
    const text = Buffer.from(content).toString('utf-8');
    return { content: [{ type: 'text', text }] };
}

async function vscodeWriteFile(filePath, content) {
    const resolved = resolvePath(filePath);
    const uri = vscode.Uri.file(resolved);
    const dir = path.dirname(resolved);
    // Ensure directory exists
    if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
    }
    const buf = Buffer.from(content, 'utf-8');
    await vscode.workspace.fs.writeFile(uri, buf);
    return { content: [{ type: 'text', text: `File written: ${resolved}` }] };
}

async function vscodeEditFile(filePath, oldText, newText) {
    const resolved = resolvePath(filePath);
    const uri = vscode.Uri.file(resolved);
    const raw = await vscode.workspace.fs.readFile(uri);
    const text = Buffer.from(raw).toString('utf-8');
    if (!text.includes(oldText)) {
        return { content: [{ type: 'text', text: `Error: oldText not found in ${resolved}` }], isError: true };
    }
    const updated = text.replace(oldText, newText);
    await vscode.workspace.fs.writeFile(uri, Buffer.from(updated, 'utf-8'));
    return { content: [{ type: 'text', text: `File edited: ${resolved}` }] };
}

async function vscodeListDirectory(dirPath) {
    const resolved = resolvePath(dirPath);
    const uri = vscode.Uri.file(resolved);
    const entries = await vscode.workspace.fs.readDirectory(uri);
    const listing = entries.map(([name, type]) => `${type === 2 ? '📁' : '📄'} ${name}`).join('\n');
    return { content: [{ type: 'text', text: listing || '(empty directory)' }] };
}

async function vscodeSearchCodebase(pattern, fileTypes) {
    const results = [];
    const findFilesPattern = fileTypes
        ? `**/*.{${fileTypes.split(',').map(s => s.trim()).join(',')}}`
        : '**/*';

    const files = await vscode.workspace.findFiles(findFilesPattern, '**/node_modules/**');
    const isRegex = isRegexPattern(pattern);

    for (const file of files.slice(0, 200)) { // Limit to 200 files
        try {
            const raw = await vscode.workspace.fs.readFile(file);
            const text = Buffer.from(raw).toString('utf-8');
            const lines = text.split('\n');
            for (let i = 0; i < lines.length; i++) {
                const match = isRegex
                    ? (() => { try { return new RegExp(pattern, 'gi').test(lines[i]); } catch { return false; } })()
                    : lines[i].toLowerCase().includes(pattern.toLowerCase());
                if (match) {
                    results.push(`${file.fsPath}:${i + 1}: ${lines[i].trim().substring(0, 200)}`);
                }
            }
        } catch { /* skip binary/unreadable files */ }
    }

    const text = results.length > 0
        ? results.slice(0, 100).join('\n') + (results.length > 100 ? `\n... and ${results.length - 100} more matches` : '')
        : `No matches found for "${pattern}"`;
    return { content: [{ type: 'text', text }] };
}

function isRegexPattern(pattern) {
    return /[\\^$.*+?()[\]{}|]/.test(pattern) && pattern.length > 2;
}

async function vscodeExecuteCommand(command, timeoutSec) {
    const cp = require('child_process');
    const timeout = (timeoutSec || 30) * 1000;
    const folders = vscode.workspace.workspaceFolders;
    const cwd = folders ? folders[0].uri.fsPath : process.cwd();

    return new Promise((resolve) => {
        const proc = cp.exec(command, { cwd, timeout, maxBuffer: 1024 * 1024 }, (err, stdout, stderr) => {
            const text = stdout + (stderr ? '\n[stderr]\n' + stderr : '');
            const truncated = text.length > 5000 ? text.substring(0, 5000) + '...' : text;
            if (err && err.killed) {
                resolve({ content: [{ type: 'text', text: `Command timed out after ${timeoutSec}s` }], isError: true });
            } else {
                resolve({ content: [{ type: 'text', text: truncated || '(no output)' }] });
            }
        });
    });
}

async function vscodeGetDiagnostics(filePath) {
    let diagnostics;
    if (filePath) {
        const uri = vscode.Uri.file(resolvePath(filePath));
        diagnostics = vscode.languages.getDiagnostics(uri);
    } else {
        diagnostics = vscode.languages.getDiagnostics();
        // Flat map to one array of all diagnostics
        const all = [];
        for (const [uri, diags] of diagnostics) {
            for (const d of diags) {
                all.push({ file: uri.fsPath, ...d });
            }
        }
        const text = all.length > 0
            ? all.map(d => `${d.file}:${d.range.start.line + 1}: [${d.severity}] ${d.message}`).join('\n')
            : 'No diagnostics found';
        return { content: [{ type: 'text', text }] };
    }

    const diags = Array.isArray(diagnostics) ? diagnostics : [];
    const text = diags.length > 0
        ? diags.map(d => `Line ${d.range.start.line + 1}: [${d.severity}] ${d.message}`).join('\n')
        : 'No diagnostics found';
    return { content: [{ type: 'text', text }] };
}

async function vscodeOpenFile(filePath, line) {
    const resolved = resolvePath(filePath);
    const uri = vscode.Uri.file(resolved);
    const doc = await vscode.workspace.openTextDocument(uri);
    const options = {};
    if (line !== undefined && line > 0) {
        const pos = new vscode.Position(line - 1, 0);
        options.selection = new vscode.Range(pos, pos);
    }
    await vscode.window.showTextDocument(doc, options);
    return { content: [{ type: 'text', text: `Opened: ${resolved}` }] };
}

// ---- .mcp.json 生成 ----

/**
 * 生成 workspace/mcp.json，配置 VSCode MCP 桥接 Server
 */
function writeMCPJson(extensionPath, projectRoot) {
    const bridgeScript = path.join(extensionPath, 'server', 'vscodeMcpBridge.py');
    const workspaceDir = path.join(projectRoot, 'workspace');
    const mcpJsonPath = path.join(workspaceDir, 'mcp.json');

    // 确保 workspace 目录存在
    if (!fs.existsSync(workspaceDir)) {
        fs.mkdirSync(workspaceDir, { recursive: true });
    }

    const mcpConfig = {
        mcpServers: {
            vscode: {
                type: 'stdio',
                command: 'python',
                args: [bridgeScript],
                env: {
                    QODER_MCP_PORT: '${QODER_MCP_PORT}',
                },
                enabled: true,
            },
        },
    };

    fs.writeFileSync(mcpJsonPath, JSON.stringify(mcpConfig, null, 2), 'utf-8');
    console.log(`[QoderChat] MCP config written: ${mcpJsonPath} (bridge: ${bridgeScript}, port: ${mcpPort})`);
}

// ---- 导出 ----

module.exports = { activate, deactivate };
