#!/usr/bin/env bash
# ============================================================
#  简历优化项目 - 一键启动（在 Git Bash 中运行： ./start.sh）
#  固化清除代理环境变量，避免 Qwen-VL OCR / AI 调用 502
#  按 Ctrl+C 停止全部服务
# ============================================================
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"

# 后端（后台运行，清代理，APP_ENV=local 强制读取 .env.local 即 SQLite + DeepSeek）
cd "$ROOT/backend"
APP_ENV=local HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= NO_PROXY=* \
  .venv/Scripts/python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
BACK_PID=$!

# 前端（后台运行，清代理避免 localhost 被代理）
cd "$ROOT/frontend"
HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= NO_PROXY=* npm run dev &
FRONT_PID=$!

echo "=================================================="
echo "  简历优化服务启动中..."
echo "  后端 : http://localhost:8000"
echo "  前端 : http://localhost:3000"
echo "  按 Ctrl+C 停止全部服务"
echo "=================================================="

cleanup() {
  echo ""
  echo "正在停止服务..."
  kill "$BACK_PID" 2>/dev/null || true
  kill "$FRONT_PID" 2>/dev/null || true
  exit 0
}
trap cleanup INT TERM
wait
