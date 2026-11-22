#!/bin/bash
set -e
cd "$(dirname "$0")"
PY="$(command -v python3)"

"$PY" -m pip show pyinstaller >/dev/null 2>&1 || "$PY" -m pip install pyinstaller

rm -rf build dist 自嘲熊.app
"$PY" -m PyInstaller --noconfirm --windowed --name 自嘲熊 \
  --paths .deps \
  --hidden-import AppKit --hidden-import Foundation --hidden-import Quartz \
  --hidden-import objc --hidden-import PIL \
  --add-data "assets/sprite.png:assets" \
  --osx-bundle-identifier com.bearpet.zichao \
  main.py
find "dist/自嘲熊.app" -name '.DS_Store' -delete 2>/dev/null || true
xattr -cr "dist/自嘲熊.app" 2>/dev/null || true
codesign --force --deep -s - "dist/自嘲熊.app" 2>/dev/null || true
cp -R "dist/自嘲熊.app" .
echo "已生成 自嘲熊.app（自带 Python，不依赖系统环境）"
