#!/usr/bin/env bash
# 项目回归测试 — 合并前必跑（见 docs/REGRESSION_POLICY.md）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
log() { printf '[regression] %s\n' "$*"; }

PY="${ROOT}/backend/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  log "未找到 backend/.venv，请先运行: bash scripts/dev-v2.sh 或 ensure_backend_venv"
  exit 1
fi

log "backend pytest…"
(cd "$ROOT/backend" && "$PY" -m pytest tests/ -q)

log "frontend-v2 vitest…"
(cd "$ROOT/frontend-v2" && npm test -- --run)

log "回归测试通过"
