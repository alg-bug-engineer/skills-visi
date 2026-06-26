#!/usr/bin/env bash
# frontend-v2 联调冒烟：健康检查 + 会话 + 流式诊断（含 problem_evidence）
set -euo pipefail

BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:8011}"
FRONTEND_URL="${FRONTEND_URL:-http://127.0.0.1:5568}"
PROMPT="${PROMPT:-奥体西路与经十路交叉口，晚高峰南北向经常拥堵，垂直方向不能溢出}"

log() { printf '[e2e-v2] %s\n' "$*"; }

log "后端健康…"
curl -sf "${BACKEND_URL}/health" | head -c 200
echo

log "前端页面…"
code=$(curl -sf -o /dev/null -w "%{http_code}" "${FRONTEND_URL}/")
[[ "$code" == "200" ]] || { log "前端不可达: ${code}"; exit 1; }

log "创建会话…"
SESSION=$(curl -sf -X POST "${BACKEND_URL}/api/v1/sessions" -H 'Content-Type: application/json')
SID=$(echo "$SESSION" | python3 -c "import sys,json; print(json.load(sys.stdin)['session_id'])")
log "session_id=${SID}"

log "流式诊断（截取 SSE）…"
TMP=$(mktemp)
curl -sf -N -X POST "${BACKEND_URL}/api/v1/sessions/${SID}/messages/stream" \
  -H 'Content-Type: application/json' \
  -d "$(python3 -c "import json; print(json.dumps({'content': '''${PROMPT}'''}))")" \
  >"$TMP" || true

grep -q 'problem_evidence' "$TMP" && log "✓ SSE 含 problem_evidence" || log "⚠ 未见到 problem_evidence（可能 mock 或数据缺失）"
grep -q '"event": "result"' "$TMP" && log "✓ 收到 result 事件" || { log "✗ 无 result"; exit 1; }

python3 - <<'PY' "$TMP"
import json, sys
path = sys.argv[1]
result = None
for block in open(path):
    if not block.startswith("data: "): continue
    try:
        ev = json.loads(block[6:])
    except Exception:
        continue
    if ev.get("event") == "result":
        result = ev.get("data", {})
if not result:
    sys.exit("no result payload")
meta = result.get("meta") or {}
pe = meta.get("problem_evidence")
qc = meta.get("quantitative_constraints")
print("state:", result.get("state"))
print("problem_evidence:", "yes" if pe else "no")
print("quantitative_constraints:", "yes" if qc else "no")
if qc:
    print("constraint narrative:", (qc.get("narrative") or "")[:80])
PY

rm -f "$TMP"
log "联调冒烟完成"
