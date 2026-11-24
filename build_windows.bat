@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -m pip show pyinstaller >nul 2>nul || python -m pip install pyinstaller
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
python -m PyInstaller --noconfirm --onefile --windowed --name 自嘲熊 ^
  --paths .deps --hidden-import PIL --collect-submodules PIL ^
  --add-data "main.py;." ^
  --add-data "bearpet;bearpet" ^
  --add-data "assets;assets" ^
  bootstrap.py
copy /Y "dist\自嘲熊.exe" "自嘲熊.exe" >nul
echo 已生成 自嘲熊.exe（自带 Python，双击即用，启动时自动检查更新）
pause
