#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_PORT="${NOVEL_API_PORT:-8004}"
WEB_PORT="${NOVEL_WEB_PORT:-5179}"

stop_port() {
  local port="$1"
  local pids
  pids="$(lsof -nP -tiTCP:"${port}" -sTCP:LISTEN 2>/dev/null || true)"

  if [[ -z "$pids" ]]; then
    echo "端口 ${port} 未运行服务"
    return
  fi

  echo "停止端口 ${port}：${pids}"
  kill $pids 2>/dev/null || true
  for _ in {1..10}; do
    lsof -nP -tiTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1 || return
    sleep 1
  done

  pids="$(lsof -nP -tiTCP:"${port}" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "$pids" ]]; then
    echo "端口 ${port} 未在等待期内退出，强制停止：${pids}"
    kill -KILL $pids 2>/dev/null || true
  fi
}

stop_port "$API_PORT"
stop_port "$WEB_PORT"
rm -f "$ROOT/backend/logs/backend.pid" "$ROOT/web-dev.pid"
echo "本地剧本刷服务已停止"
