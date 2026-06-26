#!/usr/bin/env bash
# ECS 生产环境 — 原生部署（Python uvicorn + Nginx 静态，非 Docker）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BACKEND_PORT="${PORT:-8011}"
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

BACKEND_PORT="${PORT:-8011}"
# 前端对外端口，默认 5568（与 dev-v2 一致）；禁止使用 80
HTTP_PORT="${HTTP_PORT:-5568}"
if [[ "$HTTP_PORT" == "80" ]]; then
  log "禁止使用 80 端口。请设置 HTTP_PORT（推荐 5568），例如:"
  log "  HTTP_PORT=5568 bash scripts/prod-start.sh"
  exit 1
fi

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

# shellcheck source=lib/python.sh
source "${ROOT}/scripts/lib/python.sh"

# --- Backend venv ---
if ! ensure_backend_venv "$ROOT"; then
  exit 1
fi
# shellcheck disable=SC1091
source "${ROOT}/backend/.venv/bin/activate"
log "安装/更新后端依赖…"
pip install -q --upgrade pip
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

# --- Nginx 静态资源（www-data 须可读；/root 下不可直接托管）---
DEFAULT_PUBLIC_STATIC="/var/www/intersection-agent/frontend-v2/dist"
NGINX_STATIC_ROOT="${NGINX_STATIC_ROOT:-}"

run_privileged() {
  if [[ "$(id -u)" -eq 0 ]]; then
    "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo "$@"
  else
    return 1
  fi
}

publish_static_dist() {
  local src="${ROOT}/frontend-v2/dist"
  local dest=$1
  if [[ ! -d "$src" ]]; then
    log "缺少构建产物 ${src}"
    return 1
  fi
  run_privileged mkdir -p "$dest"
  if command -v rsync >/dev/null 2>&1; then
    run_privileged rsync -a --delete "${src}/" "${dest}/"
  else
    run_privileged rm -rf "${dest:?}/"*
    run_privileged cp -a "${src}/." "${dest}/"
  fi
  run_privileged chown -R www-data:www-data "$dest" 2>/dev/null \
    || run_privileged chmod -R a+rX "$dest"
}

resolve_nginx_static_root() {
  local dest
  if [[ -n "$NGINX_STATIC_ROOT" ]]; then
    dest="$NGINX_STATIC_ROOT"
  elif [[ "$DEPLOY_ROOT" == /root/* ]]; then
    dest="$DEFAULT_PUBLIC_STATIC"
    log "项目在 /root 下，Nginx(www-data) 无法读取；同步静态文件到 ${dest}"
  else
    dest="${DEPLOY_ROOT}/frontend-v2/dist"
  fi
  if [[ "$dest" != "${ROOT}/frontend-v2/dist" ]]; then
    publish_static_dist "$dest"
  elif [[ "$DEPLOY_ROOT" == /root/* ]]; then
    publish_static_dist "$dest"
  else
    # 非 /root 部署也确保 nginx 可读
    run_privileged chmod -R a+rX "${dest}" 2>/dev/null || true
  fi
  printf '%s' "$dest"
}

STATIC_ROOT="$(resolve_nginx_static_root)"
echo "$STATIC_ROOT" >"${LOG_DIR}/nginx-static-root"

# --- Nginx ---
render_nginx_conf() {
  local conf_src="${ROOT}/deploy/nginx.host.conf"
  local tmp_conf
  tmp_conf="$(mktemp)"
  sed -e "s|__STATIC_ROOT__|${STATIC_ROOT}|g" \
      -e "s|__HTTP_PORT__|${HTTP_PORT}|g" \
      -e "s|__BACKEND_PORT__|${BACKEND_PORT}|g" \
      "$conf_src" >"$tmp_conf"
  printf '%s' "$tmp_conf"
}

setup_nginx() {
  local tmp_conf site_name="${NGINX_SITE_NAME:-intersection-agent}"
  local installed=0

  tmp_conf="$(render_nginx_conf)"

  # Ubuntu/Debian 常用 sites-available（与本机 ppt.conf 同目录）
  if [[ -d /etc/nginx/sites-available ]]; then
    if run_privileged cp "$tmp_conf" "/etc/nginx/sites-available/${site_name}.conf"; then
      run_privileged ln -sf "/etc/nginx/sites-available/${site_name}.conf" \
        "/etc/nginx/sites-enabled/${site_name}.conf" || true
      run_privileged rm -f /etc/nginx/conf.d/intersection-agent.conf 2>/dev/null || true
      installed=1
      log "Nginx 配置已写入 sites-available/${site_name}.conf"
    fi
  fi

  # 回退 conf.d
  if [[ "$installed" -eq 0 && -d /etc/nginx/conf.d ]]; then
    if run_privileged cp "$tmp_conf" /etc/nginx/conf.d/intersection-agent.conf; then
      installed=1
      log "Nginx 配置已写入 conf.d/intersection-agent.conf"
    fi
  fi

  rm -f "$tmp_conf"

  if [[ "$installed" -eq 0 ]]; then
    log "无法写入 Nginx 配置，请手动: sudo cp deploy/nginx.host.conf /etc/nginx/sites-available/${site_name}.conf"
    return 1
  fi

  if ! run_privileged nginx -t; then
    log "nginx -t 失败，配置未生效，请检查上方错误"
    return 1
  fi

  run_privileged systemctl reload nginx 2>/dev/null \
    || run_privileged nginx -s reload 2>/dev/null \
    || true

  log "Nginx 已重载，监听 HTTP 端口: ${HTTP_PORT}，静态: ${STATIC_ROOT}"
  return 0
}

verify_deploy() {
  sleep 1
  local ok_health=0 ok_home=0
  if curl -sf "http://127.0.0.1:${HTTP_PORT}/health" >/dev/null 2>&1; then
    ok_health=1
    log "本机验证通过: http://127.0.0.1:${HTTP_PORT}/health"
  fi
  if curl -sf "http://127.0.0.1:${HTTP_PORT}/" >/dev/null 2>&1; then
    ok_home=1
    log "本机验证通过: http://127.0.0.1:${HTTP_PORT}/"
  fi
  if [[ "$ok_health" -eq 1 && "$ok_home" -eq 1 ]]; then
    return 0
  fi
  if [[ "$ok_health" -eq 1 && "$ok_home" -eq 0 ]]; then
    log "警告: /health 正常但首页 500 — 多为 Nginx 无权读静态目录"
    log "静态 root: ${STATIC_ROOT}"
    log "请确认已重新部署；或查看: sudo tail -20 /var/log/nginx/error.log"
  else
    log "警告: 本机 http://127.0.0.1:${HTTP_PORT}/ 不可达"
    log "请运行: bash scripts/prod-check.sh"
  fi
  if command -v ss >/dev/null 2>&1; then
    log "当前监听端口:"
    ss -tlnp 2>/dev/null | grep -E ":(${HTTP_PORT}|${BACKEND_PORT}) " || true
  fi
  return 1
}

if command -v nginx >/dev/null 2>&1; then
  if setup_nginx; then
    verify_deploy || true
  else
    log "Nginx 配置失败，见 deploy/README.md 手动配置"
  fi
else
  log "未检测到 Nginx。生产环境请安装 Nginx 并配置 deploy/nginx.host.conf"
  log "临时访问: BIND_HOST=0.0.0.0 bash scripts/dev-v2.sh"
fi

log "=========================================="
log "  部署方式  原生（uvicorn + Nginx）"
log "  前端      http://<ECS公网IP>:${HTTP_PORT}/  （勿用 https）"
log "  健康检查  http://<ECS公网IP>:${HTTP_PORT}/health"
log "  自检      bash scripts/prod-check.sh"
log "  后端日志  tail -f ${BACKEND_LOG}"
log "  停止服务  bash scripts/prod-stop.sh"
log "=========================================="
