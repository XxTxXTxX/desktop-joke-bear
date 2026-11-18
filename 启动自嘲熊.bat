@echo off
chcp 65001 >nul
cd /d "%~dp0"
where pythonw >nul 2>nul
if errorlevel 1 (
  start "" "C:\Python315\pythonw.exe" "%~dp0main.py"
) else (
  start "" pythonw "%~dp0main.py"
)
exit /b 0
