#!/usr/bin/env bash
# 生产部署自检：Nginx 监听、本机 curl、后端健康
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

HTTP_PORT="${HTTP_PORT:-5568}"
BACKEND_PORT="${PORT:-8011}"

if [[ -f "${ROOT}/backend/.env" ]]; then
  # shellcheck disable=SC1091
  set -a
  source "${ROOT}/backend/.env"
  set +a
  HTTP_PORT="${HTTP_PORT:-5568}"
  BACKEND_PORT="${PORT:-8011}"
fi

log() { printf '[prod-check] %s\n' "$*"; }
ok() { log "OK  $*"; }
fail() { log "FAIL $*"; }

errors=0

log "========== 部署自检 =========="
log "HTTP_PORT=${HTTP_PORT}  BACKEND_PORT=${BACKEND_PORT}"
log ""

if curl -sf "http://127.0.0.1:${BACKEND_PORT}/health" >/dev/null 2>&1; then
  ok "后端 http://127.0.0.1:${BACKEND_PORT}/health"
else
  fail "后端未响应，请查看 .prod-logs/backend.log"
  errors=$((errors + 1))
fi

if command -v ss >/dev/null 2>&1; then
  if ss -tlnp 2>/dev/null | grep -q ":${HTTP_PORT} "; then
    ok "端口 ${HTTP_PORT} 正在监听"
    ss -tlnp 2>/dev/null | grep ":${HTTP_PORT} " || true
  else
    fail "端口 ${HTTP_PORT} 未监听 — Nginx 可能未加载本服务配置"
    errors=$((errors + 1))
  fi
fi

if curl -sf "http://127.0.0.1:${HTTP_PORT}/health" >/dev/null 2>&1; then
  ok "Nginx 反代 http://127.0.0.1:${HTTP_PORT}/health"
else
  fail "Nginx 未在 ${HTTP_PORT} 提供 /health"
  errors=$((errors + 1))
fi

if curl -sf "http://127.0.0.1:${HTTP_PORT}/" >/dev/null 2>&1; then
  ok "前端静态 http://127.0.0.1:${HTTP_PORT}/"
else
  fail "前端首页不可达"
  errors=$((errors + 1))
fi

log ""
log "--- Nginx 配置位置 ---"
for f in \
  /etc/nginx/sites-enabled/intersection-agent.conf \
  /etc/nginx/sites-available/intersection-agent.conf \
  /etc/nginx/conf.d/intersection-agent.conf; do
  [[ -f "$f" ]] && log "  存在: $f"
done

if command -v nginx >/dev/null 2>&1; then
  log ""
  log "--- nginx -T 中 listen ${HTTP_PORT} ---"
  nginx -T 2>/dev/null | grep -E "listen.*${HTTP_PORT}" || log "  （未找到 listen ${HTTP_PORT}）"
fi

log ""
log "--- 访问说明 ---"
log "  请使用 HTTP（无 SSL）：http://<公网IP>:${HTTP_PORT}/"
log "  不要用 https:// — 5568 未配置证书"
log ""
if [[ -d "${ROOT}/frontend-v2/dist" ]]; then
  ok "dist 目录存在: ${ROOT}/frontend-v2/dist"
else
  fail "缺少 frontend-v2/dist，请先 bash scripts/prod-start.sh"
  errors=$((errors + 1))
fi

log ""
if [[ "$errors" -eq 0 ]]; then
  log "自检通过。若外网仍不可达，请检查阿里云安全组是否放行 ${HTTP_PORT}/tcp（ufw 之外还有一层）。"
  exit 0
fi
log "发现 ${errors} 项问题。可重新部署: bash scripts/prod-start.sh"
exit 1
