#!/usr/bin/env bash
# ECS 开发模式 — 与本地 dev-v2 相同：uvicorn + npm run dev，无需 build / Nginx
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BACKEND_PORT="${PORT:-8011}"
FRONTEND_PORT="${HTTP_PORT:-5568}"
BIND_HOST="${BIND_HOST:-0.0.0.0}"
LOG_DIR="${ROOT}/.prod-logs"
BACKEND_LOG="${LOG_DIR}/backend-dev.log"
FRONTEND_LOG="${LOG_DIR}/frontend-v2-dev.log"
PID_FILE="${LOG_DIR}/pids-dev"

log() { printf '[prod-dev] %s\n' "$*"; }

mkdir -p "$LOG_DIR"

if [[ "$FRONTEND_PORT" == "80" ]]; then
  log "禁止使用 80 端口"
  exit 1
fi

run_privileged() {
  if [[ "$(id -u)" -eq 0 ]]; then "$@"
  elif command -v sudo >/dev/null 2>&1; then sudo "$@"
  else return 1; fi
}

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

# 若 prod-start 配过 Nginx 占 5568，开发模式需先卸掉该站点
if [[ -L /etc/nginx/sites-enabled/intersection-agent.conf ]] \
   || [[ -f /etc/nginx/sites-enabled/intersection-agent.conf ]]; then
  if command -v ss >/dev/null 2>&1 && ss -tlnp 2>/dev/null | grep -q ":${FRONTEND_PORT}.*nginx"; then
    log "停用 Nginx intersection-agent 站点，改由 Vite 监听 ${FRONTEND_PORT}"
    run_privileged rm -f /etc/nginx/sites-enabled/intersection-agent.conf 2>/dev/null || true
    run_privileged nginx -s reload 2>/dev/null || run_privileged systemctl reload nginx 2>/dev/null || true
    sleep 1
  fi
fi

# shellcheck source=lib/python.sh
source "${ROOT}/scripts/lib/python.sh"
if ! ensure_backend_venv "$ROOT"; then exit 1; fi

# shellcheck disable=SC1091
source "${ROOT}/backend/.venv/bin/activate"

if [[ ! -d "${ROOT}/frontend-v2/node_modules" ]]; then
  log "安装 frontend-v2 依赖…"
  cd "${ROOT}/frontend-v2" && npm ci
fi

kill_port "$BACKEND_PORT" "backend"
kill_port "$FRONTEND_PORT" "frontend-v2"

log "启动后端 uvicorn ${BIND_HOST}:${BACKEND_PORT}…"
cd "${ROOT}/backend"
nohup uvicorn intersection_agent.main:app \
  --host "$BIND_HOST" --port "$BACKEND_PORT" \
  >"$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!

ok=0
for _ in $(seq 1 40); do
  curl -sf "http://127.0.0.1:${BACKEND_PORT}/health" >/dev/null 2>&1 && ok=1 && break
  sleep 0.5
done
[[ "$ok" -eq 1 ]] || { log "后端启动失败: $BACKEND_LOG"; exit 1; }

log "启动 Vite 开发服 npm run dev (:${FRONTEND_PORT})…"
cd "${ROOT}/frontend-v2"
export VITE_DEV_PROXY_TARGET="http://127.0.0.1:${BACKEND_PORT}"
export VITE_DEBUG_LOG=1
nohup npm run dev -- --host "$BIND_HOST" --port "$FRONTEND_PORT" --strictPort \
  >"$FRONTEND_LOG" 2>&1 &
FRONTEND_PID=$!

ok=0
for _ in $(seq 1 60); do
  curl -sf "http://127.0.0.1:${FRONTEND_PORT}/" >/dev/null 2>&1 && ok=1 && break
  sleep 0.5
done
[[ "$ok" -eq 1 ]] || { log "前端启动失败: $FRONTEND_LOG"; tail -20 "$FRONTEND_LOG"; exit 1; }

{
  echo "$BACKEND_PID backend"
  echo "$FRONTEND_PID frontend-v2"
} >"$PID_FILE"

log "=========================================="
log "  模式      开发（无 build、无 Nginx 静态）"
log "  前端      http://<公网IP>:${FRONTEND_PORT}/"
log "  后端      http://127.0.0.1:${BACKEND_PORT}/health（Vite 反代 /api）"
log "  前端日志  tail -f ${FRONTEND_LOG}"
log "  后端日志  tail -f ${BACKEND_LOG}"
log "  停止      kill \$(cat ${PID_FILE} | awk '{print \$1}') 2>/dev/null; bash scripts/prod-stop.sh"
log "=========================================="
