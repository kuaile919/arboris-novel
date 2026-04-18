@echo off
chcp 65001 >nul
echo ========================================
echo   Arboris-Novel 启动脚本
echo ========================================
echo.

REM 设置 Node.js 路径（如果需要）
set PATH=D:\develop\nodejs;%PATH%

REM 检查 Node.js 版本
echo Node.js 版本:
node -v
echo.

REM 检查 .env 文件
if not exist "backend\.env" (
    echo [警告] backend\.env 文件不存在
    echo 请参考 deploy\docker-compose.yml 中的环境变量配置
    echo.
)

REM 启动后端（直接使用系统Python，不依赖虚拟环境）
echo [1/2] 启动后端服务...
start "Backend - FastAPI" cmd /k "cd /d %~dp0backend && uvicorn app.main:app --reload --reload-dir app --reload-dir prompts --port 8000"

REM 等待后端启动
echo 等待后端启动...
timeout /t 3 /nobreak >nul

REM 启动前端
echo [2/2] 启动前端服务...
start "Frontend - Vite" cmd /k "set PATH=D:\develop\nodejs;%PATH% && cd /d %~dp0frontend && npm run dev"

echo.
echo ========================================
echo   服务已启动!
echo   后端: http://127.0.0.1:8000
echo   前端: http://127.0.0.1:5173
echo   API文档: http://127.0.0.1:8000/docs
echo ========================================
echo.
pause
