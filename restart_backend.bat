@echo off
chcp 65001 >nul
echo ========================================
echo   重启后端服务
echo ========================================
echo.

REM 杀掉已有的后端进程
echo [1/2] 关闭后端服务...
taskkill /F /FI "WINDOWTITLE eq Backend*" 2>nul
timeout /t 1 /nobreak >nul

REM 启动后端
echo [2/2] 启动后端服务...
start "Backend - FastAPI" cmd /k "cd /d %~dp0backend && uvicorn app.main:app --reload --reload-dir app --reload-dir prompts --port 8000"

echo.
echo ========================================
echo   后端已重启!
echo   后端: http://127.0.0.1:8000
echo   API文档: http://127.0.0.1:8000/docs
echo ========================================
echo.
