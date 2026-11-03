#!/usr/bin/env bash
# MyAgentConfig 通用安装器（macOS / Linux）
# 具体装哪些东西由 components/*/manifest.json 决定，本脚本只负责转发。
set -u
SOURCE="${BASH_SOURCE[0]}"
while [ -h "$SOURCE" ]; do
  DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  case "$SOURCE" in
    /*) ;;
    *) SOURCE="$DIR/$SOURCE" ;;
  esac
done
REPO="$(cd -P "$(dirname "$SOURCE")" && pwd)"

if ! command -v python3 >/dev/null 2>&1; then
  echo "需要 python3（安装器与 gwf 引擎都是纯 Python 实现）" >&2
  exit 1
fi

exec python3 "$REPO/tools/install.py" "$@"
