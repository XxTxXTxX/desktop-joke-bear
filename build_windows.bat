@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -m pip show pyinstaller >nul 2>nul || python -m pip install pyinstaller
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if not exist C:\DeskBear mkdir C:\DeskBear
python -m PyInstaller --noconfirm --onefile --windowed --runtime-tmpdir C:/DeskBear/runtime --name 自嘲熊 ^
  --paths .deps ^
  --add-data "main.py;." ^
  --add-data "bearpet;bearpet" ^
  --add-data "assets;assets" ^
  bootstrap.py
copy /Y "dist\自嘲熊.exe" "自嘲熊.exe" >nul
if not exist C:\DeskBear mkdir C:\DeskBear
copy /Y "dist\自嘲熊.exe" "C:\DeskBear\自嘲熊.exe" >nul
powershell -NoProfile -Command "$ws=New-Object -ComObject WScript.Shell; $sc=$ws.CreateShortcut([Environment]::GetFolderPath('Desktop')+'\自嘲熊.lnk'); $sc.TargetPath='C:\DeskBear\自嘲熊.exe'; $sc.WorkingDirectory='C:\DeskBear'; $sc.Save()"
echo 已生成自嘲熊.exe，并安装到 C:\DeskBear（桌面已创建快捷方式）
pause
