@echo off
chcp 65001 >nul
echo ========================================
echo   重启所有服务
echo ========================================
echo.

REM 设置 Node.js 路径
set PATH=D:\develop\nodejs;%PATH%

REM 杀掉已有的进程
echo [1/3] 关闭所有服务...
taskkill /F /FI "WINDOWTITLE eq Backend*" 2>nul
taskkill /F /FI "WINDOWTITLE eq Frontend*" 2>nul
timeout /t 2 /nobreak >nul

REM 启动后端
echo [2/3] 启动后端服务...
start "Backend - FastAPI" cmd /k "cd /d %~dp0backend && uvicorn app.main:app --reload --reload-dir app --reload-dir prompts --port 8000"

REM 等待后端启动
echo 等待后端启动...
timeout /t 3 /nobreak >nul

REM 启动前端
echo [3/3] 启动前端服务...
start "Frontend - Vite" cmd /k "set PATH=D:\develop\nodejs;%PATH% && cd /d %~dp0frontend && npm run dev"

echo.
echo ========================================
echo   所有服务已重启!
echo   后端: http://127.0.0.1:8000
echo   前端: http://127.0.0.1:5173
echo   API文档: http://127.0.0.1:8000/docs
echo ========================================
echo.
