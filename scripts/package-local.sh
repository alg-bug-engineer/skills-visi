#!/usr/bin/env bash
# 本地项目打包：产出可解压即用的 tar.gz（含各类 .env，不含依赖目录）。
#
# 默认排除：
#   references/  .venv/  .pytest_cache/
#   frontend/node_modules/  frontend/playwright-report/
#   以及 dist/、.git/、logs/、__pycache__/、前端构建与测试产物
#
# 会带上（若存在）：
#   .env  .env.example  frontend/.env.local  frontend/.env.example
#   及其他未被排除的本地文件（如 gitignore 的密钥文档）
#
# 用法：
#   bash scripts/package-local.sh
#   INCLUDE_GIT=1 bash scripts/package-local.sh
#   OUT_DIR=/tmp bash scripts/package-local.sh
#
# 警告：产物含密钥，勿上传公开网盘 / 勿提交到 git。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
OUT_DIR="${OUT_DIR:-${ROOT_DIR}/dist}"
STAMP="$(date +%Y%m%d-%H%M%S)"
BASENAME="traffic-agent-local-${STAMP}"
ARCHIVE="${OUT_DIR}/${BASENAME}.tar.gz"
INCLUDE_GIT="${INCLUDE_GIT:-0}"

mkdir -p "${OUT_DIR}"

TMP_PARENT="$(mktemp -d)"
cleanup() { rm -rf "${TMP_PARENT}"; }
trap cleanup EXIT

STAGE="${TMP_PARENT}/${BASENAME}"
mkdir -p "${STAGE}"

RSYNC_EXCLUDES=(
  --exclude 'references/'
  --exclude '.venv/'
  --exclude '.pytest_cache/'
  --exclude 'frontend/node_modules/'
  --exclude 'frontend/playwright-report/'
  --exclude 'dist/'
  --exclude 'logs/'
  --exclude '__pycache__/'
  --exclude '.DS_Store'
  --exclude 'frontend/test-results/'
  --exclude 'frontend/coverage/'
  --exclude 'frontend/dist/'
)

if [ "${INCLUDE_GIT}" != "1" ]; then
  RSYNC_EXCLUDES+=(--exclude '.git/')
fi

echo "⚠ 打包将包含本地 env / 密钥文件（若存在），请勿公开分发。"
echo "▶ 根目录：${ROOT_DIR}"
echo "▶ 输出：  ${ARCHIVE}"

rsync -a "${RSYNC_EXCLUDES[@]}" "${ROOT_DIR}/" "${STAGE}/"

# 避免 macOS 资源叉
export COPYFILE_DISABLE=1
tar -czf "${ARCHIVE}" -C "${TMP_PARENT}" "${BASENAME}"

echo "▶ 校验归档…"
tar -tzf "${ARCHIVE}" >/dev/null

ENV_LIST="$(tar -tzf "${ARCHIVE}" | grep -E '(^|/)\.env(\.|$)|(^|/)\.env\.local$|(^|/)\.env\.example$' || true)"
if [ -n "${ENV_LIST}" ]; then
  echo "✓ 已包含的 env 相关路径："
  echo "${ENV_LIST}" | sed 's/^/    /'
else
  echo "⚠ 包内未发现 .env / .env.local（本地可能尚未创建）"
fi

# 确认关键排除目录未打入
for bad in references .venv .pytest_cache frontend/node_modules frontend/playwright-report; do
  if tar -tzf "${ARCHIVE}" | grep -q "/${bad}/"; then
    echo "✗ 排除失败：包内仍含 ${bad}" >&2
    exit 1
  fi
done

SIZE="$(du -h "${ARCHIVE}" | awk '{print $1}')"
echo "✓ 完成：${ARCHIVE}（${SIZE}）"
echo "  解压：tar -xzf \"${ARCHIVE}\""
