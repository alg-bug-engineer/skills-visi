#!/usr/bin/env bash
# ECS 生产环境 — 原生部署（Python uvicorn + Nginx 静态，非 Docker）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BACKEND_PORT="${PORT:-8011}"
HTTP_PORT="${HTTP_PORT:-80}"
LOG_DIR="${ROOT}/.prod-logs"
BACKEND_LOG="${LOG_DIR}/backend.log"
PID_FILE="${LOG_DIR}/pids"
DEPLOY_ROOT="${DEPLOY_ROOT:-$ROOT}"

log() { printf '[prod-start] %s\n' "$*"; }

mkdir -p "$LOG_DIR"

if [[ ! -f "${ROOT}/backend/.env" ]]; then
  log "缺少 backend/.env，请先: cp backend/.env.example backend/.env 并填写配置"
  exit 1
fi

# shellcheck disable=SC1091
set -a
source "${ROOT}/backend/.env"
set +a

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
  curl -sf "http://127.0.0.1:${BACKEND_PORT}/health" >/dev/null 2>&1
}

# --- Backend venv ---
if [[ ! -d "${ROOT}/backend/.venv" ]]; then
  log "创建 Python 虚拟环境…"
  python3 -m venv "${ROOT}/backend/.venv"
fi
# shellcheck disable=SC1091
source "${ROOT}/backend/.venv/bin/activate"
log "安装/更新后端依赖…"
pip install -q -e "${ROOT}/backend"

# --- Frontend build ---
if [[ ! -d "${ROOT}/frontend-v2/node_modules" ]]; then
  log "安装 frontend-v2 依赖…"
  cd "${ROOT}/frontend-v2" && npm ci
else
  cd "${ROOT}/frontend-v2"
fi

log "构建 frontend-v2 生产包（VITE_API_BASE= 同源反代）…"
export VITE_API_BASE=""
npm run build
cd "$ROOT"

# --- Start backend ---
kill_port "$BACKEND_PORT" "backend"
log "启动后端 uvicorn 0.0.0.0:${BACKEND_PORT}…"
cd "${ROOT}/backend"
nohup uvicorn intersection_agent.main:app \
  --host "${HOST:-0.0.0.0}" \
  --port "$BACKEND_PORT" \
  >"$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!
cd "$ROOT"

ok=0
for _ in $(seq 1 40); do
  if backend_healthy; then ok=1; break; fi
  sleep 0.5
done
if [[ "$ok" -ne 1 ]]; then
  log "后端启动失败，请查看 ${BACKEND_LOG}"
  tail -n 30 "$BACKEND_LOG" 2>/dev/null || true
  exit 1
fi
log "后端就绪 http://127.0.0.1:${BACKEND_PORT}/health"

echo "$BACKEND_PID backend" >"$PID_FILE"

# --- Nginx ---
setup_nginx() {
  local conf_src="${ROOT}/deploy/nginx.host.conf"
  local dist_path="${DEPLOY_ROOT}/frontend-v2/dist"
  local tmp_conf
  tmp_conf="$(mktemp)"

  sed "s|/var/www/intersection-agent|${DEPLOY_ROOT}|g" "$conf_src" >"$tmp_conf"

  if [[ -d /etc/nginx/conf.d ]]; then
    if [[ -w /etc/nginx/conf.d ]]; then
      cp "$tmp_conf" /etc/nginx/conf.d/intersection-agent.conf
    elif command -v sudo >/dev/null 2>&1; then
      sudo cp "$tmp_conf" /etc/nginx/conf.d/intersection-agent.conf
    else
      log "无法写入 /etc/nginx/conf.d，请手动复制 deploy/nginx.host.conf"
      rm -f "$tmp_conf"
      return 1
    fi
    rm -f "$tmp_conf"
    if command -v nginx >/dev/null 2>&1; then
      if sudo nginx -t 2>/dev/null || nginx -t 2>/dev/null; then
        sudo systemctl reload nginx 2>/dev/null || sudo nginx -s reload 2>/dev/null || nginx -s reload 2>/dev/null || true
        log "Nginx 已重载，静态目录: ${dist_path}"
        return 0
      fi
    fi
  fi
  rm -f "$tmp_conf"
  return 1
}

if command -v nginx >/dev/null 2>&1; then
  if setup_nginx; then
  :
  else
    log "Nginx 配置需手动完成，见 deploy/README.md"
  fi
else
  log "未检测到 Nginx。生产环境请安装 Nginx 并配置 deploy/nginx.host.conf"
  log "临时访问: 将 frontend-v2/dist 部署到 Web 服务器，或开发模式 BIND_HOST=0.0.0.0 bash scripts/dev-v2.sh"
fi

log "=========================================="
log "  部署方式  原生（uvicorn + Nginx）"
log "  前端      http://<ECS公网IP>:${HTTP_PORT}/"
log "  健康检查  http://<ECS公网IP>:${HTTP_PORT}/health"
log "  后端日志  tail -f ${BACKEND_LOG}"
log "  停止服务  bash scripts/prod-stop.sh"
log "=========================================="
