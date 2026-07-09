#!/usr/bin/env bash
# 解析 ECS 公网 IP，供启动脚本打印访问地址与 Vite 公网模式配置。
# 优先 PUBLIC_HOST 环境变量，其次阿里云元数据 eipv4。

resolve_public_host() {
  if [ -n "${PUBLIC_HOST:-}" ]; then
    printf '%s' "${PUBLIC_HOST}"
    return 0
  fi

  local ip=""
  ip="$(curl -sf --connect-timeout 1 http://100.100.100.200/latest/meta-data/eipv4 2>/dev/null || true)"
  if [ -n "${ip}" ]; then
    printf '%s' "${ip}"
    return 0
  fi

  ip="$(curl -sf --connect-timeout 1 http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || true)"
  if [ -n "${ip}" ]; then
    printf '%s' "${ip}"
    return 0
  fi

  return 1
}

verify_port_listening() {
  local port="$1"
  local label="${2:-端口 ${port}}"

  if command -v ss >/dev/null 2>&1; then
    if ss -tlnH "sport = :${port}" 2>/dev/null | grep -q .; then
      echo "✓ ${label} 监听中："
      ss -tlnp "sport = :${port}" 2>/dev/null || ss -tln "sport = :${port}" 2>/dev/null
      if ss -tlnH "sport = :${port}" 2>/dev/null | grep -q '127.0.0.1:'; then
        if ! ss -tlnH "sport = :${port}" 2>/dev/null | grep -Eq '(\*|0\.0\.0\.0|\[::\]):'; then
          echo "⚠️  ${label} 仅监听 127.0.0.1，公网无法访问；请确认 --host 0.0.0.0"
          return 1
        fi
      fi
      return 0
    fi
  fi

  if command -v lsof >/dev/null 2>&1; then
    if lsof -nP -iTCP:"${port}" -sTCP:LISTEN 2>/dev/null | grep -q .; then
      echo "✓ ${label} 监听中："
      lsof -nP -iTCP:"${port}" -sTCP:LISTEN 2>/dev/null || true
      return 0
    fi
  fi

  echo "✗ ${label} 未检测到 LISTEN"
  return 1
}

print_access_banner() {
  local frontend_port="${1:-5173}"
  local backend_port="${2:-8000}"
  local public_host=""
  local mode="${ECS_PUBLIC_ACCESS:-0}"

  public_host="$(resolve_public_host || true)"

  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  if [ "${mode}" = "1" ] && [ -n "${public_host}" ]; then
    echo "  模式：ECS 公网（build + preview，origin 固定为公网 IP）"
  else
    echo "  模式：开发（vite dev，已绑定 0.0.0.0）"
  fi
  echo "  说明：阿里云 EIP 不在本机网卡上，不能改为只绑定公网 IP；"
  echo "        须监听 0.0.0.0，由安全组/EIP 转发到本机端口。"
  if [ -n "${public_host}" ]; then
    echo "  ★ 请用浏览器打开： http://${public_host}:${frontend_port}"
    echo "  （勿在你自己电脑上用 localhost — 那只指向你自己的机器）"
    echo "  API 由前端服务代理 → 127.0.0.1:${backend_port}"
  else
    echo "  公网访问： export PUBLIC_HOST=<ECS公网IP> ECS_PUBLIC_ACCESS=1"
    echo "  示例：     export PUBLIC_HOST=8.149.232.39 ECS_PUBLIC_ACCESS=1"
  fi
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""
}

print_firewall_hints() {
  local port="${1:-5173}"
  echo "▶ 若公网仍无法访问，在 ECS 上自查："
  echo "    ss -tlnp | grep :${port}"
  echo "    sudo ufw status | grep ${port}"
  echo "    curl -I http://127.0.0.1:${port}/"
  echo "    阿里云控制台 → 安全组入方向 → TCP ${port}"
}
