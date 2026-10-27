#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST_ARCH="$(uname -m)"
ARCH="${NOVEL_DESKTOP_ARCH:-$HOST_ARCH}"

case "$ARCH" in
  arm64|x64) ;;
  x86_64) ARCH="x64" ;;
  *) echo "不支持的 macOS 架构：$ARCH（支持 arm64 或 x64）" >&2; exit 1 ;;
esac

cd "$ROOT"
echo "构建 macOS $ARCH 安装包..."
npm run build
npm run desktop:backend
npx electron-forge make --platform=darwin --arch="$ARCH"

echo "构建完成：$ROOT/out/make"
