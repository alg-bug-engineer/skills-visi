#!/usr/bin/env bash
# 清空本地 Skill 包目录，便于真实环境重复测试。
# Usage:
#   bash scripts/clear_skills.sh          # 使用 .env 中 SKILL_DIR_PATH
#   bash scripts/clear_skills.sh --force  # 不询问直接删除
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  set -a
  source .env
  set +a
fi

SKILL_DIR="${SKILL_DIR_PATH:-data/skills}"

if [[ ! -d "$SKILL_DIR" ]]; then
  echo "Skill 目录不存在，无需清理: $SKILL_DIR"
  exit 0
fi

shopt -s nullglob
dirs=("$SKILL_DIR"/*/)
shopt -u nullglob

COUNT=0
for d in "${dirs[@]}"; do
  base=$(basename "$d")
  [[ "$base" == _template ]] && continue
  [[ "$base" == .gitkeep ]] && continue
  COUNT=$((COUNT + 1))
done

echo "当前 Skill 包数量: $COUNT"
echo "目标目录: $ROOT/$SKILL_DIR"

if [[ "$COUNT" -eq 0 ]]; then
  echo "目录内无 Skill 包，无需清理"
  exit 0
fi

if [[ "${1:-}" != "--force" ]]; then
  read -r -p "确认删除全部 Skill 包？[y/N] " ans
  if [[ "${ans,,}" != "y" ]]; then
    echo "已取消"
    exit 0
  fi
fi

for d in "${dirs[@]}"; do
  base=$(basename "$d")
  [[ "$base" == _template ]] && continue
  rm -rf "$d"
done

# 清理遗留的单文件 JSON（旧格式）
rm -f "$SKILL_DIR"/*.json 2>/dev/null || true

echo "✅ 已删除 $COUNT 个 Skill 包"
