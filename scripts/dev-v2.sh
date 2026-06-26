#!/usr/bin/env bash
# 一键启动后端 + frontend-v2（5568）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_PORT=8011
FRONTEND_PORT=5568
# 本地开发默认 127.0.0.1；ECS/局域网调试可设 BIND_HOST=0.0.0.0
BIND_HOST="${BIND_HOST:-127.0.0.1}"
BACKEND_HOST="${BIND_HOST}"
LOG_DIR="${ROOT}/.dev-logs"
BACKEND_LOG="${LOG_DIR}/backend.log"
FRONTEND_LOG="${LOG_DIR}/frontend-v2.log"
PID_FILE="${LOG_DIR}/pids-v2"

mkdir -p "$LOG_DIR"

log() { printf '[dev-v2] %s\n' "$*"; }

kill_port() {
  local port=$1 name=$2 pids=""
  if command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -ti "tcp:${port}" -sTCP:LISTEN 2>/dev/null || true)"
  fi
  if [[ -n "$pids" ]]; then
    log "清理端口 ${port} (${name}): ${pids}"
    # shellcheck disable=SC2086
    kill ${pids} 2>/dev/null || true
    sleep 1
  fi
}

backend_healthy() {
  curl -sf "http://${BACKEND_HOST}:${BACKEND_PORT}/health" >/dev/null 2>&1
}

CLEANED_UP=0
cleanup() {
  [[ "$CLEANED_UP" -eq 1 ]] && return
  CLEANED_UP=1
  log "停止服务…"
  [[ -n "${BACKEND_PID:-}" ]] && kill "$BACKEND_PID" 2>/dev/null || true
  [[ -n "${FRONTEND_PID:-}" ]] && kill "$FRONTEND_PID" 2>/dev/null || true
  kill_port "$FRONTEND_PORT" "frontend-v2"
  # 仅停止本脚本拉起的后端，避免误杀外部复用的进程
  if [[ -n "${BACKEND_PID:-}" ]]; then
    kill_port "$BACKEND_PORT" "backend"
  fi
  rm -f "$PID_FILE"
}
trap cleanup INT TERM

if [[ ! -d "${ROOT}/backend/.venv" ]]; then
  log "请先: cd backend && python3 -m venv .venv && pip install -e '.[dev]'"
  exit 1
fi

# 先清理前端端口，避免旧 vite 残留
kill_port "$FRONTEND_PORT" "frontend-v2"

BACKEND_STARTED_BY_SCRIPT=0
if backend_healthy; then
  log "后端已在 ${BACKEND_PORT} 运行，复用（Ctrl+C 不会停止该进程）"
else
  kill_port "$BACKEND_PORT" "backend"
  # shellcheck disable=SC1091
  source "${ROOT}/backend/.venv/bin/activate"
  log "启动后端…"
  cd "${ROOT}/backend"
  nohup uvicorn intersection_agent.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" \
    >"$BACKEND_LOG" 2>&1 &
  BACKEND_PID=$!
  BACKEND_STARTED_BY_SCRIPT=1
  ok=0
  for _ in $(seq 1 40); do
    if backend_healthy; then
      ok=1
      break
    fi
    sleep 0.5
  done
  if [[ "$ok" -ne 1 ]]; then
    log "后端启动失败，请查看 ${BACKEND_LOG}"
    tail -n 20 "$BACKEND_LOG" 2>/dev/null || true
    exit 1
  fi
  log "后端就绪 http://${BACKEND_HOST}:${BACKEND_PORT}/health"
fi

if [[ ! -d "${ROOT}/frontend-v2/node_modules" ]]; then
  log "安装 frontend-v2 依赖…"
  cd "${ROOT}/frontend-v2" && npm install
fi

log "启动 frontend-v2 (:${FRONTEND_PORT})…"
cd "${ROOT}/frontend-v2"
export VITE_DEV_PROXY_TARGET="http://${BACKEND_HOST}:${BACKEND_PORT}"
export VITE_DEBUG_LOG=1
nohup npm run dev -- --host "$BIND_HOST" --port "$FRONTEND_PORT" --strictPort \
  >"$FRONTEND_LOG" 2>&1 &
FRONTEND_PID=$!

ok=0
for _ in $(seq 1 40); do
  curl -sf "http://${BIND_HOST}:${FRONTEND_PORT}/" >/dev/null 2>&1 && ok=1 && break
  sleep 0.5
done
if [[ "$ok" -ne 1 ]]; then
  log "前端启动失败，请查看 ${FRONTEND_LOG}"
  exit 1
fi

{
  echo "${BACKEND_PID:-} backend"
  echo "$FRONTEND_PID frontend-v2"
} >"$PID_FILE"

log "=========================================="
log "  v2 前端  http://${BIND_HOST}:${FRONTEND_PORT}"
log "  后端     http://${BACKEND_HOST}:${BACKEND_PORT}/health"
if [[ "$BACKEND_STARTED_BY_SCRIPT" -eq 0 ]]; then
  log "  提示     后端为外部进程，Ctrl+C 仅停前端"
fi
log "=========================================="
tail -f "$FRONTEND_LOG"
