@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".bear.pid" (
  echo 没找到 .bear.pid，可能还没启动过。
  pause
  exit /b 1
)
set /p PID=<.bear.pid
echo 正在关闭自嘲熊 pid=%PID% ...
taskkill /PID %PID% >nul 2>nul
timeout /t 2 >nul
taskkill /PID %PID% /F >nul 2>nul
if exist ".bear.pid" del ".bear.pid" >nul 2>nul
echo 已关闭。
timeout /t 1 >nul
exit /b 0
