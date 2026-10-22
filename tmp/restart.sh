#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_PORT="${NOVEL_API_PORT:-8004}"
WEB_PORT="${NOVEL_WEB_PORT:-5179}"
NO_PULL="${NOVEL_SKIP_PULL:-0}"
NO_INSTALL="${NOVEL_SKIP_INSTALL:-0}"

export NO_PROXY="127.0.0.1,localhost,::1${NO_PROXY:+,$NO_PROXY}"
export no_proxy="$NO_PROXY"

stop_port() {
  local port="$1"
  local pids
  pids="$(lsof -nP -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  [[ -z "$pids" ]] && return
  echo "停止端口 $port：$pids"
  kill $pids 2>/dev/null || true
  for _ in {1..10}; do
    lsof -nP -tiTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1 || return
    sleep 1
  done
  pids="$(lsof -nP -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  [[ -n "$pids" ]] && kill -KILL $pids 2>/dev/null || true
}

select_python() {
  for candidate in python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      echo "$candidate"
      return
    fi
  done
  echo "未找到 Python 3.11+，请先安装 Python。" >&2
  exit 1
}

cd "$ROOT"

if [[ "$NO_PULL" != "1" ]]; then
  echo "拉取最新代码..."
  git pull --ff-only
fi

PYTHON_BIN="${NOVEL_PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(select_python)"
fi
if [[ ! -x "$ROOT/backend/.venv/bin/python" ]]; then
  echo "创建 Python 虚拟环境..."
  "$PYTHON_BIN" -m venv "$ROOT/backend/.venv"
fi

if [[ "$NO_INSTALL" != "1" ]]; then
  echo "安装后端依赖..."
  "$ROOT/backend/.venv/bin/python" -m pip install -r "$ROOT/backend/requirements.txt"
  echo "安装前端依赖..."
  npm install --workspaces --no-audit --no-fund
fi

stop_port "$API_PORT"
stop_port "$WEB_PORT"
mkdir -p "$ROOT/backend/logs"

echo "启动后端 :$API_PORT..."
(
  cd "$ROOT/backend"
  nohup "$ROOT/backend/.venv/bin/python" -m uvicorn main:app --host 0.0.0.0 --port "$API_PORT" > "$ROOT/backend/logs/server.log" 2>&1 &
  echo $! > "$ROOT/backend/logs/backend.pid"
)

echo "启动前端 :$WEB_PORT..."
(
  cd "$ROOT/web"
  nohup npm run dev -- --host 0.0.0.0 --port "$WEB_PORT" > "$ROOT/web-dev.log" 2>&1 &
  echo $! > "$ROOT/web-dev.pid"
)

for _ in {1..60}; do
  if curl -fsS "http://127.0.0.1:$API_PORT/health" >/dev/null 2>&1 && curl -fsS "http://127.0.0.1:$WEB_PORT" >/dev/null 2>&1; then
    echo "Novel 已就绪："
    echo "  Web: http://127.0.0.1:$WEB_PORT"
    echo "  API: http://127.0.0.1:$API_PORT/docs"
    exit 0
  fi
  sleep 1
done

echo "Novel 在 60 秒内未完全就绪，请查看：" >&2
echo "  $ROOT/backend/logs/server.log" >&2
echo "  $ROOT/web-dev.log" >&2
exit 1
