#!/usr/bin/env bash
# 一条命令完成全区域扫描并产出快照。
# 用法：scripts/scan.sh [--periods 早高峰,白平峰,晚高峰] [--concurrency 4]
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
PY="${REGION_SCAN_PYTHON:-$HERE/../backend/.venv/bin/python}"

cd "$HERE"
exec "$PY" -m region_scan.cli scan "$@"
