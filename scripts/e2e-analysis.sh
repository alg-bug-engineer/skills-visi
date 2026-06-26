#!/usr/bin/env bash
# E2E：诊断流程 — 无顶部步骤条、右侧理解过程、地图 HUD/标注、固化确认
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_URL="${FRONTEND_URL:-http://127.0.0.1:5567}"
BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:8011}"
CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
PWCLI="$CODEX_HOME/skills/playwright/scripts/playwright_cli.sh"
WAIT_SEC="${E2E_WAIT_SEC:-100}"

log() { printf '[e2e] %s\n' "$*"; }
fail() { printf '[e2e] FAIL: %s\n' "$*" >&2; exit 1; }

log "检查后端健康…"
curl -sf "$BACKEND_URL/api/v1/health" >/dev/null || fail "后端未就绪: $BACKEND_URL"

command -v npx >/dev/null 2>&1 || fail "需要 npx（Node.js）"
[[ -x "$PWCLI" ]] || fail "未找到 playwright-cli: $PWCLI"

log "打开前端 $FRONTEND_URL"
"$PWCLI" open "$FRONTEND_URL" >/dev/null
sleep 2

log "发送示例诊断请求…"
"$PWCLI" snapshot >/dev/null
"$PWCLI" eval "document.querySelector('[data-testid=send-button]')?.click()" >/dev/null

log "等待分析完成（${WAIT_SEC}s）…"
sleep "$WAIT_SEC"

RAW="$("$PWCLI" eval "JSON.stringify({
  processBar: !!document.querySelector('.process-bar'),
  hud: !!document.querySelector('.map-hud'),
  hudTitle: document.querySelector('.map-hud .hud-title')?.textContent || '',
  markers: document.querySelectorAll('.map-marker').length,
  steps: document.querySelectorAll('.step-item').length,
  confirm: !!document.querySelector('.confirm-bubble')
})" 2>/dev/null)"

RESULT="$(printf '%s\n' "$RAW" | sed -n 's/^"//;s/"$//p' | grep '^{' | tail -1 | sed 's/\\"/"/g')"
if [[ -z "$RESULT" ]]; then
  RESULT="$(printf '%s\n' "$RAW" | grep -oE '\{[^{}]*\}' | tail -1)"
fi
[[ -n "$RESULT" ]] || fail "无法解析页面探测结果"

log "DOM 探测结果: $RESULT"

echo "$RESULT" | grep -q '"processBar":false' || fail "顶部流程步骤条仍存在"
echo "$RESULT" | grep -q '"hud":true' || fail "地图 HUD 未显示"
echo "$RESULT" | grep -q '"markers":[1-9]' || fail "地图数据标注未显示"
echo "$RESULT" | grep -q '"steps":[1-9]' || fail "右侧理解过程无步骤"
echo "$RESULT" | grep -q '"confirm":true' || fail "固化确认气泡未出现"

log "全部断言通过"
