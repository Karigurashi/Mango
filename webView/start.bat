@echo off
chcp 65001 >nul
title 蓝图编辑器

REM 将 Node.js 加入 PATH（避免 %PATH% 在引号内被拆成 %P + ATH%）
if exist "D:\Coder\NodeJs\node.exe" (
    for %%G in ("D:\Coder\NodeJs") do set "PATH=%%~G;%PATH%"
)

echo 启动后端 (8765)...
cd /d "%~dp0.."
start "后端" cmd /k "py -3 -m uvicorn webView.server.llmServer:app --host 127.0.0.1 --port 8765"

echo 启动前端 (5173)...
cd /d "%~dp0"
start "前端" cmd /k "npm run dev"

echo.
echo 后端启动需要几秒，稍后访问: http://localhost:5173/
echo 关闭本窗口不会停止前后端，请在对应窗口按 Ctrl+C 退出。
pause
