#!/usr/bin/env bash
# 停止 dev.sh 启动的前后端服务，并清理端口残留
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_PORT=8011
FRONTEND_PORT=5567
PID_FILE="${ROOT}/.dev-logs/pids"

log() {
  printf '[stop] %s\n' "$*"
}

kill_port() {
  local port=$1
  local name=$2
  local pids=""

  if command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -ti "tcp:${port}" -sTCP:LISTEN 2>/dev/null || true)"
  fi

  if [[ -z "$pids" ]]; then
    log "端口 ${port} (${name}) 无进程"
    return 0
  fi

  log "终止端口 ${port} (${name}): ${pids}"
  # shellcheck disable=SC2086
  kill ${pids} 2>/dev/null || true
  sleep 0.5
  pids="$(lsof -ti "tcp:${port}" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "$pids" ]]; then
    # shellcheck disable=SC2086
    kill -9 ${pids} 2>/dev/null || true
  fi
}

if [[ -f "$PID_FILE" ]]; then
  while read -r pid name; do
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      log "停止 ${name} pid=${pid}"
      kill "$pid" 2>/dev/null || true
    fi
  done < "$PID_FILE"
  rm -f "$PID_FILE"
fi

kill_port "$BACKEND_PORT" "backend"
kill_port "$FRONTEND_PORT" "frontend"
log "完成"
