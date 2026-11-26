@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -m pip show pyinstaller >nul 2>nul || python -m pip install pyinstaller
taskkill /IM "自嘲熊.exe" /F >nul 2>nul
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
python -m PyInstaller --noconfirm --onedir --windowed --icon "assets\icon.ico" --name 自嘲熊 ^
  --paths .deps ^
  --add-data "main.py;." ^
  --add-data "bearpet;bearpet" ^
  --add-data "assets;assets" ^
  bootstrap.py
rem 安装到 C:\DeskBear\自嘲熊\（exe 与 _internal 必须同目录）
if exist "C:\DeskBear\自嘲熊" rmdir /s /q "C:\DeskBear\自嘲熊"
xcopy /E /I /Y "dist\自嘲熊" "C:\DeskBear\自嘲熊" >nul
rem 仓库目录也同步一份，双击仓库里的自嘲熊.exe 可直接运行
if exist "_internal" rmdir /s /q "_internal"
xcopy /E /I /Y "dist\自嘲熊" "." >nul
rem 清掉旧的单文件版和它的 runtime 目录
if exist "C:\DeskBear\自嘲熊.exe" del /Q "C:\DeskBear\自嘲熊.exe"
if exist "C:\DeskBear\runtime" rmdir /s /q "C:\DeskBear\runtime"
powershell -NoProfile -Command "$ws=New-Object -ComObject WScript.Shell; $sc=$ws.CreateShortcut([Environment]::GetFolderPath('Desktop')+'\自嘲熊.lnk'); $sc.TargetPath='C:\DeskBear\自嘲熊\自嘲熊.exe'; $sc.WorkingDirectory='C:\DeskBear\自嘲熊'; $sc.IconLocation='C:\DeskBear\自嘲熊\自嘲熊.exe,0'; $sc.Save()"
echo 已生成 onedir 版本，并安装到 C:\DeskBear\自嘲熊（桌面快捷方式已更新）
pause
