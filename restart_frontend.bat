@echo off
chcp 65001 >nul
echo ========================================
echo   重启前端服务
echo ========================================
echo.

REM 设置 Node.js 路径
set PATH=D:\develop\nodejs;%PATH%

REM 杀掉已有的前端进程
echo [1/2] 关闭前端服务...
taskkill /F /FI "WINDOWTITLE eq Frontend*" 2>nul
timeout /t 1 /nobreak >nul

REM 启动前端
echo [2/2] 启动前端服务...
start "Frontend - Vite" cmd /k "set PATH=D:\develop\nodejs;%PATH% && cd /d %~dp0frontend && npm run dev"

echo.
echo ========================================
echo   前端已重启!
echo   前端: http://127.0.0.1:5173
echo ========================================
echo.
