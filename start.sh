#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend"
BACKEND_HOST="${BACKEND_HOST:-0.0.0.0}"
FRONTEND_HOST="${FRONTEND_HOST:-0.0.0.0}"

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  echo
  echo "正在停止服务..."

  if [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi

  if [[ -n "$FRONTEND_PID" ]] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
    kill "$FRONTEND_PID" 2>/dev/null || true
  fi

  wait 2>/dev/null || true
  echo "已退出。"
}

trap cleanup SIGINT SIGTERM EXIT

echo "========================================"
echo "  Arboris-Novel 一键启动（Linux）"
echo "========================================"
echo

if [[ ! -f "$BACKEND_DIR/.env" ]]; then
  echo "[警告] 未找到 backend/.env"
  echo "请参考 deploy/docker-compose.yml 配置环境变量。"
  echo
fi

echo "[1/2] 启动后端..."
cd "$BACKEND_DIR"

if [[ ! -d ".venv" ]]; then
  echo "创建 Python 虚拟环境..."
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install -r requirements.txt -q
uvicorn app.main:app --reload --reload-dir app --reload-dir prompts --host "$BACKEND_HOST" --port 8000 &
BACKEND_PID=$!
echo "后端 PID: $BACKEND_PID"

echo "等待后端启动..."
sleep 3

echo "[2/2] 启动前端..."
cd "$FRONTEND_DIR"
npm install --silent
npm run dev -- --host "$FRONTEND_HOST" --port 5173 &
FRONTEND_PID=$!
echo "前端 PID: $FRONTEND_PID"

echo
echo "========================================"
echo "  启动完成"
echo "  后端: http://$BACKEND_HOST:8000"
echo "  前端: http://$FRONTEND_HOST:5173"
echo "  API 文档: http://$BACKEND_HOST:8000/docs"
echo "  按 Ctrl+C 一键停止"
echo "========================================"
echo

wait
