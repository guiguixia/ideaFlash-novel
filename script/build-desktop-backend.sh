#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${NOVEL_PYTHON_BIN:-$ROOT/backend/.venv/bin/python}"
OUTPUT_DIR="$ROOT/desktop/bin"
TEMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TEMP_DIR"' EXIT
export PYINSTALLER_CONFIG_DIR="$TEMP_DIR/pyinstaller-config"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "未找到 Python 虚拟环境：$PYTHON_BIN" >&2
  echo "请先按 README 创建 backend/.venv。" >&2
  exit 1
fi

mkdir -p "$OUTPUT_DIR"
"$PYTHON_BIN" -m pip install -r "$ROOT/backend/requirements-desktop.txt"
"$PYTHON_BIN" -m PyInstaller --noconfirm --clean --onefile --name novel-server \
  --paths "$ROOT/backend" \
  --distpath "$OUTPUT_DIR" \
  --workpath "$TEMP_DIR/work" \
  --specpath "$TEMP_DIR/spec" \
  "$ROOT/backend/desktop_server.py"

echo "已生成本地服务：$OUTPUT_DIR/novel-server"
