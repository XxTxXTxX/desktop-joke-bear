@echo off
chcp 65001 >nul
cd /d "%~dp0"
where pythonw >nul 2>nul
if errorlevel 1 (
  start "" "C:\Python315\pythonw.exe" "%~dp0启动自嘲熊.py"
) else (
  start "" pythonw "%~dp0启动自嘲熊.py"
)
exit /b 0
