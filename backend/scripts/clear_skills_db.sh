#!/usr/bin/env bash
# 兼容旧脚本名，转发到 clear_skills.sh
exec "$(cd "$(dirname "$0")" && pwd)/clear_skills.sh" "$@"
