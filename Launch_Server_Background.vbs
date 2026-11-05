' CommitMaster — Launch Central Server in background (no console window)
Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
currentDir = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = currentDir

' Determine Python executable
pyExe = "python.exe"
If fso.FileExists(WshShell.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python\Python312\python.exe")) Then
    pyExe = WshShell.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python\Python312\python.exe")
End If

cmdLine = """" & pyExe & """ """ & currentDir & "\server.py"" --host 0.0.0.0 --port 8000"
WshShell.Run cmdLine, 0, False

