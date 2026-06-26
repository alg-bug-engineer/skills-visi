#!/usr/bin/env bash
# 停止生产环境后端进程
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="${ROOT}/.prod-logs/pids"
BACKEND_PORT="${PORT:-8011}"

log() { printf '[prod-stop] %s\n' "$*"; }

kill_port() {
  local port=$1 name=$2 pids=""
  if command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -ti "tcp:${port}" -sTCP:LISTEN 2>/dev/null || true)"
  fi
  if [[ -n "$pids" ]]; then
    log "停止端口 ${port} (${name}): ${pids}"
    # shellcheck disable=SC2086
    kill ${pids} 2>/dev/null || true
  fi
}

if [[ -f "$PID_FILE" ]]; then
  while read -r pid role; do
    [[ -z "$pid" ]] && continue
    if kill -0 "$pid" 2>/dev/null; then
      log "停止 ${role} (pid ${pid})"
      kill "$pid" 2>/dev/null || true
    fi
  done <"$PID_FILE"
  rm -f "$PID_FILE"
fi

kill_port "$BACKEND_PORT" "backend"
log "已停止"
