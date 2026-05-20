' Silent launcher for claude-telegram-startup.bat
' Lives in the Windows Startup folder so it fires at logon.
' windowstyle=0 keeps the cmd window completely hidden.
Set WshShell = CreateObject("WScript.Shell")
batPath = WshShell.ExpandEnvironmentStrings("%USERPROFILE%\boot-scripts\claude-telegram-startup.bat")
WshShell.Run "cmd /c """ & batPath & """", 0, False
