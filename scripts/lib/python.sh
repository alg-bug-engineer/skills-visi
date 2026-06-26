#!/usr/bin/env bash
# 解析 Python 3.11+ 解释器，供 prod-start.sh / dev-v2.sh 使用

python_version_ok() {
  local py=$1
  "$py" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null
}

resolve_python311() {
  local candidates=()
  [[ -n "${PYTHON_BIN:-}" ]] && candidates+=("$PYTHON_BIN")
  candidates+=(python3.12 python3.11 python3)
  local c
  for c in "${candidates[@]}"; do
    if command -v "$c" >/dev/null 2>&1 && python_version_ok "$c"; then
      command -v "$c"
      return 0
    fi
  done
  return 1
}

python311_install_hint() {
  cat <<'EOF'
未找到 Python 3.11+。后端要求 requires-python >= 3.11。

Ubuntu / Debian:
  sudo apt update
  sudo apt install -y python3.11 python3.11-venv python3.11-dev
  rm -rf backend/.venv
  PYTHON_BIN=python3.11 bash scripts/prod-start.sh

Alibaba Cloud Linux 3 / CentOS（deadsnakes 或源码）:
  sudo dnf install -y python3.11 python3.11-devel
  # 若无 3.11 包，可用 pyenv 或官方源码编译安装

也可指定解释器:
  PYTHON_BIN=/usr/bin/python3.11 bash scripts/prod-start.sh
EOF
}

ensure_backend_venv() {
  local root=$1
  local py venv="${root}/backend/.venv"

  py="$(resolve_python311)" || {
    python311_install_hint
    return 1
  }

  printf '[python] 使用 %s (%s)\n' "$py" "$("$py" --version 2>&1)"

  if [[ -d "$venv" ]]; then
    if ! "${venv}/bin/python" -c 'import sys; assert sys.version_info >= (3, 11)' 2>/dev/null; then
      local old_ver
      old_ver="$("${venv}/bin/python" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo unknown)"
      printf '[python] 现有 .venv 为 Python %s，需要 3.11+，正在重建…\n' "$old_ver"
      rm -rf "$venv"
    fi
  fi

  if [[ ! -d "$venv" ]]; then
    printf '[python] 创建虚拟环境…\n'
    "$py" -m venv "$venv"
  fi
}
