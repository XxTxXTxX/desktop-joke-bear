#!/bin/bash
cd "$(dirname "$0")" || exit 1
PID_FILE=".bear.pid"
if [ ! -f "$PID_FILE" ]; then
  PID_FILE="$HOME/Library/Application Support/自嘲熊/.bear.pid"
fi
if [ -f "$PID_FILE" ]; then
  PID=$(cat "$PID_FILE")
  if [ -n "$PID" ]; then
    echo "正在关闭自嘲熊 pid=$PID ..."
    kill "$PID" 2>/dev/null
    for _ in 1 2 3 4 5; do
      kill -0 "$PID" 2>/dev/null || break
      sleep 0.4
    done
    kill -9 "$PID" 2>/dev/null
    rm -f "$PID_FILE"
  fi
fi
pkill -f "自嘲熊.app/Contents/MacOS/自嘲熊" 2>/dev/null
pkill -f "desktop-joke-bear/.*/main.py" 2>/dev/null
echo "已关闭。"
