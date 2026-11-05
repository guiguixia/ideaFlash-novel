#!/usr/bin/env bash
set -euo pipefail

novel_dev_url="http://127.0.0.1:5179"

# 开发服务已在运行时直接复用它，避免 Vite 因 strictPort 报端口占用。
if curl --noproxy '*' -fsS --max-time 2 "$novel_dev_url/" >/dev/null; then
  ELECTRON_START_URL="$novel_dev_url" ./node_modules/.bin/electron .
  exit $?
fi

./node_modules/.bin/concurrently -k -n web,electron -c magenta,cyan \
  "npm run dev:web" \
  "./node_modules/.bin/wait-on $novel_dev_url && ELECTRON_START_URL=$novel_dev_url ./node_modules/.bin/electron ."
