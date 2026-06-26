#!/usr/bin/env bash
# End-to-end curl tests for intersection agent API.
# Usage: bash scripts/curl_tests.sh [BASE_URL]
set -euo pipefail

BASE="${1:-http://localhost:8000}"
PASS=0
FAIL=0

assert_contains() {
  local desc="$1"
  local haystack="$2"
  local needle="$3"
  if echo "$haystack" | grep -q "$needle"; then
    echo "✅ $desc"
    PASS=$((PASS + 1))
  else
    echo "❌ $desc (expected: $needle)"
    echo "$haystack"
    FAIL=$((FAIL + 1))
  fi
}

echo "=== Health ==="
HEALTH=$(curl -s "$BASE/health")
assert_contains "health ok" "$HEALTH" '"status":"ok"'

echo "=== Full diagnosis flow ==="
SID=$(curl -s -X POST "$BASE/api/v1/sessions" | python3 -c "import sys,json; print(json.load(sys.stdin)['session_id'])")
R1=$(curl -s -X POST "$BASE/api/v1/sessions/$SID/messages" \
  -H "Content-Type: application/json" \
  -d '{"content":"奥体西路与经十路交叉口，下午四点南北向经常拥堵，应该绿灯更长一点"}')
assert_contains "suggestion ready" "$R1" 'awaiting_create'
assert_contains "suggestion generated" "$R1" 'suggestion'
R2=$(curl -s -X POST "$BASE/api/v1/sessions/$SID/messages" \
  -H "Content-Type: application/json" \
  -d '{"content":"确认固化"}')
assert_contains "skill created" "$R2" 'skill_created'

echo "=== NLU follow-up (missing time) ==="
SID2=$(curl -s -X POST "$BASE/api/v1/sessions" | python3 -c "import sys,json; print(json.load(sys.stdin)['session_id'])")
F1=$(curl -s -X POST "$BASE/api/v1/sessions/$SID2/messages" \
  -H "Content-Type: application/json" \
  -d '{"content":"缺少时段：奥体西路与经十路交叉口经常拥堵"}')
assert_contains "follow up time" "$F1" 'follow_up'

F2=$(curl -s -X POST "$BASE/api/v1/sessions/$SID2/messages" \
  -H "Content-Type: application/json" \
  -d '{"content":"下午四点南北向"}')
assert_contains "complete after follow up" "$F2" 'diagnosis\|awaiting_confirm\|follow_up'

echo "=== Deny suggestion confirmation ==="
SID3=$(curl -s -X POST "$BASE/api/v1/sessions" | python3 -c "import sys,json; print(json.load(sys.stdin)['session_id'])")
curl -s -X POST "$BASE/api/v1/sessions/$SID3/messages" \
  -H "Content-Type: application/json" \
  -d '{"content":"奥体西路与经十路交叉口，下午四点南北向经常拥堵"}' > /dev/null
D1=$(curl -s -X POST "$BASE/api/v1/sessions/$SID3/messages" \
  -H "Content-Type: application/json" \
  -d '{"content":"不是"}')
assert_contains "deny suggestion" "$D1" '未生成治理建议'

echo "=== Intersection not found ==="
SID4=$(curl -s -X POST "$BASE/api/v1/sessions" | python3 -c "import sys,json; print(json.load(sys.stdin)['session_id'])")
N1=$(curl -s -X POST "$BASE/api/v1/sessions/$SID4/messages" \
  -H "Content-Type: application/json" \
  -d '{"content":"未知路口ABC与DEF路交叉口，下午四点南北向拥堵"}')
assert_contains "not found or follow up" "$N1" 'error\|follow_up\|暂无'

echo "=== List skills ==="
SK=$(curl -s "$BASE/api/v1/skills")
assert_contains "skills list" "$SK" 'skill_id'

echo ""
echo "Results: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
