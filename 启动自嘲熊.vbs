' 无控制台窗口启动自嘲熊桌面宠物
Option Explicit
Dim sh, fso, dir
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = dir
On Error Resume Next
sh.Run "pythonw.exe """ & dir & "\main.py""", 0, False
If Err.Number <> 0 Then
    sh.Run "C:\Python315\pythonw.exe """ & dir & "\main.py""", 0, False
End If
