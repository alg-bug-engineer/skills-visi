#!/usr/bin/env bash
# 边界场景全覆盖测试（NLU 追问、路口变体、时段、治理建议、Skill 等）
#
# Usage:
#   bash scripts/boundary_tests.sh [BASE_URL]
#   MOCK_LLM=0 MOCK_DB=0 bash scripts/boundary_tests.sh http://127.0.0.1:8001
#
# 真实联调前建议:
#   bash scripts/clear_skills_db.sh --force
#   python3 scripts/probe_intersection.py
#   MOCK_LLM=0 MOCK_DB=0 uvicorn intersection_agent.main:app --port 8001
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  # shell/lib .env but allow env override from command line
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

BASE="${1:-http://127.0.0.1:8001}"
PASS=0
FAIL=0
SECTION=""

# ---------- helpers ----------
log_section() {
  SECTION="$1"
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "▶ $SECTION"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

pass() {
  echo "  ✅ [$SECTION] $1"
  PASS=$((PASS + 1))
}

fail() {
  echo "  ❌ [$SECTION] $1"
  [[ -n "${2:-}" ]] && echo "     响应: $2"
  FAIL=$((FAIL + 1))
}

new_session() {
  curl -s -X POST "$BASE/api/v1/sessions" | python3 -c "import sys,json; print(json.load(sys.stdin)['session_id'])"
}

send() {
  local sid="$1"
  local content="$2"
  local payload
  payload=$(python3 -c 'import json, sys; print(json.dumps({"content": sys.argv[1]}))' "$content")
  curl -s -X POST "$BASE/api/v1/sessions/$sid/messages" \
    -H "Content-Type: application/json" \
    -d "$payload"
}

json_field() {
  local json="$1"
  local expr="$2"
  echo "$json" | python3 -c "import sys,json; d=json.load(sys.stdin); print($expr)"
}

assert_state_in() {
  local json="$1"
  local desc="$2"
  shift 2
  local states=("$@")
  local state
  state=$(json_field "$json" "d['state']")
  for s in "${states[@]}"; do
    if [[ "$state" == "$s" ]]; then
      pass "$desc (state=$state)"
      return 0
    fi
  done
  fail "$desc (state=$state, expected one of: ${states[*]})" "$json"
}

assert_reply_type_in() {
  local json="$1"
  local desc="$2"
  shift 2
  local types=("$@")
  local rtype
  rtype=$(json_field "$json" "d['reply']['type']")
  for t in "${types[@]}"; do
    if [[ "$rtype" == "$t" ]]; then
      pass "$desc (type=$rtype)"
      return 0
    fi
  done
  fail "$desc (type=$rtype)" "$json"
}

assert_has_suggestion() {
  local json="$1"
  local desc="$2"
  local delta
  delta=$(echo "$json" | python3 -c "import sys,json; d=json.load(sys.stdin); s=d.get('suggestion'); print(s.get('delta_seconds') if s else '')")
  if [[ -n "$delta" && "$delta" != "None" ]]; then
    pass "$desc (delta=${delta}s)"
  else
    fail "$desc (无 suggestion)" "$json"
  fi
}

assert_resolution_if_diagnosis() {
  local json="$1"
  local desc="$2"
  local rtype
  rtype=$(json_field "$json" "d['reply']['type']")
  if [[ "$rtype" != "diagnosis" && "$rtype" != "skill_created" ]]; then
    pass "$desc (跳过: 仍在 NLU 补全, type=$rtype)"
    return 0
  fi
  assert_resolution "$json" "$desc"
}

assert_resolution() {
  local json="$1"
  local desc="$2"
  local src
  src=$(json_field "$json" "d.get('meta',{}).get('resolution_source','')")
  if [[ -n "$src" && "$src" != "None" && "$src" != "not_found" ]]; then
    pass "$desc (source=$src)"
  else
    fail "$desc (source=$src)" "$json"
  fi
}

# ---------- 0. 健康检查 ----------
log_section "健康检查"
HEALTH=$(curl -s "$BASE/health")
if echo "$HEALTH" | grep -q '"status":"ok"'; then
  pass "服务健康"
else
  fail "服务不可用" "$HEALTH"
  echo "请先启动: uvicorn intersection_agent.main:app --port 8001"
  exit 1
fi
echo "  mock_llm=$(json_field "$HEALTH" "d.get('mock_llm')") mock_db=$(json_field "$HEALTH" "d.get('mock_db')")"

# ---------- 1. NLU 完整输入 ----------
log_section "NLU · 完整输入一次通过"
SID=$(new_session)
R=$(send "$SID" "奥体西路与经十路交叉口，下午四点南北向经常拥堵，应该绿灯更长一点")
assert_reply_type_in "$R" "返回诊断并等待固化确认" "diagnosis"
assert_state_in "$R" "等待固化确认" "awaiting_confirm"
assert_has_suggestion "$R" "生成治理建议"
assert_resolution "$R" "路口解析成功"
R_CONFIRM=$(send "$SID" "确认固化")
assert_reply_type_in "$R_CONFIRM" "确认后固化成功" "skill_created"

# ---------- 2. NLU 缺时段追问 ----------
log_section "NLU · 缺时段 → 追问 → 补全"
SID=$(new_session)
R1=$(send "$SID" "奥体西路与经十路交叉口南北向经常拥堵")
assert_reply_type_in "$R1" "追问时段" "follow_up" "text"
assert_state_in "$R1" "nlu_incomplete" "nlu_incomplete" "follow_up"

R2=$(send "$SID" "主要是下午四点到晚高峰，南北向")
assert_reply_type_in "$R2" "补全后等待治理建议确认" "follow_up"
assert_state_in "$R2" "进入确认或继续补全" "awaiting_confirm" "nlu_incomplete" "processing"

# ---------- 3. NLU 缺路口追问 ----------
log_section "NLU · 缺路口 → 追问"
SID=$(new_session)
R1=$(send "$SID" "晚高峰这里南北向很堵，绿灯感觉不够")
assert_reply_type_in "$R1" "追问路口" "follow_up"
R2=$(send "$SID" "奥体西路与经十路交叉口")
assert_state_in "$R2" "补全路口后推进" "awaiting_confirm" "nlu_incomplete" "processing" "intersection_ambiguous"

# ---------- 4. NLU 缺问题类型追问 ----------
log_section "NLU · 缺问题类型 → 追问"
SID=$(new_session)
R1=$(send "$SID" "奥体西路与经十路交叉口，早上八点南北向")
assert_reply_type_in "$R1" "追问问题类型" "follow_up"
R2=$(send "$SID" "主要是拥堵")
assert_state_in "$R2" "补全问题类型" "awaiting_confirm" "nlu_incomplete" "processing"

# ---------- 5. 路口变体（顺序/缩写/路口后缀） ----------
log_section "路口解析 · 名称变体（奥体西路 × 经十路）"
VARIANTS=(
  "经十路与奥体西路交叉口，晚高峰南北向拥堵"
  "奥体西路与经十路路口，下午四点南北向拥堵"
  "奥体西与经十路，晚高峰南北向堵车"
  "经十路和奥体西路路口，下午四点南北向经常堵"
)
for V in "${VARIANTS[@]}"; do
  SID=$(new_session)
  R=$(send "$SID" "$V")
  assert_reply_type_in "$R" "变体: ${V:0:20}..." "diagnosis" "follow_up" "error"
  assert_resolution_if_diagnosis "$R" "变体解析: ${V:0:20}..."
done

# ---------- 6. 不同时段 ----------
log_section "数据层 · 不同时段诊断"
PERIODS=(
  "奥体西路与经十路交叉口，早高峰七点南北向经常拥堵"
  "奥体西路与经十路交叉口，下午四点南北向经常拥堵"
  "奥体西路与经十路交叉口，上午十点到十一点南北向也经常拥堵"
)
for P in "${PERIODS[@]}"; do
  SID=$(new_session)
  R=$(send "$SID" "$P")
  assert_reply_type_in "$R" "时段: ${P: -8}" "follow_up" "text"
  if echo "$R" | grep -q 'awaiting_generate\|暂未命中'; then
    pass "时段诊断进入确认或未命中: ${P: -8}"
  else
    fail "时段诊断未进入预期分支: ${P: -8}" "$R"
  fi
done

# ---------- 7. 治理方案字段校验 ----------
log_section "治理建议 · 结构化输出"
SID=$(new_session)
R=$(send "$SID" "奥体西路与经十路交叉口，晚高峰南北向拥堵，绿灯应该更长")
for field in delta_seconds direction narrative confidence rule_id; do
  if echo "$R" | python3 -c "import sys,json; d=json.load(sys.stdin); s=d.get('suggestion') or {}; sys.exit(0 if '$field' in s and s['$field'] is not None else 1)"; then
    pass "suggestion.$field 存在"
  else
    fail "suggestion.$field 缺失" "$R"
  fi
done

# ---------- 8. 固化 + 快路径 ----------
log_section "Skill · 固化与快路径"
bash "$ROOT/scripts/clear_skills_db.sh" --force >/dev/null 2>&1 || true

SID=$(new_session)
R1=$(send "$SID" "奥体西路与经十路交叉口，晚高峰南北向拥堵，绿灯延长")
assert_reply_type_in "$R1" "生成建议后等待固化" "diagnosis"
assert_state_in "$R1" "等待固化确认" "awaiting_confirm"
R2=$(send "$SID" "确认固化")
assert_reply_type_in "$R2" "确认后固化成功" "skill_created"

SID2=$(new_session)
R3=$(send "$SID2" "奥体西路与经十路交叉口，晚高峰南北向拥堵")
if echo "$R3" | grep -q 'skill_fast_path\|Skill 快路径'; then
  pass "Skill 快路径命中"
else
  src=$(json_field "$R3" "d.get('meta',{}).get('matched_skill')")
  if [[ -n "$src" && "$src" != "None" && "$src" != "null" ]]; then
    pass "Skill 快路径 (matched_skill=$src)"
  else
    fail "Skill 快路径未命中" "$R3"
  fi
fi

# ---------- 9. 否定治理建议 ----------
log_section "治理建议 · 否定生成（「不是」不误触）"
SID=$(new_session)
send "$SID" "奥体西路与经十路交叉口，晚高峰南北向拥堵" >/dev/null
R=$(send "$SID" "不是")
if echo "$R" | grep -q '未生成治理建议'; then
  pass "否定治理建议"
else
  fail "否定未生效" "$R"
fi

# ---------- 10. 未知路口 ----------
log_section "路口解析 · 未知路口降级"
SID=$(new_session)
R=$(send "$SID" "火星路与月球路交叉口，晚高峰南北向拥堵")
assert_reply_type_in "$R" "未知路口处理" "error" "follow_up" "text"

# ---------- 11. 规则未命中（低饱和场景，若 mock 则可能仍命中） ----------
log_section "规则引擎 · 诊断分支"
SID=$(new_session)
R=$(send "$SID" "奥体西路与经十路交叉口，平峰时段南北向只是偶尔有点车，不太拥堵")
assert_reply_type_in "$R" "平峰弱拥堵" "diagnosis" "text" "follow_up"

# ---------- summary ----------
echo ""
echo "════════════════════════════════════════"
echo "边界测试完成: $PASS 通过, $FAIL 失败"
echo "════════════════════════════════════════"
[[ "$FAIL" -eq 0 ]]
