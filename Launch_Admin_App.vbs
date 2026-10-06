' CommitMaster — Launch Personal Admin App without console window
Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
currentDir = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = currentDir

' Ensure Desktop shortcut exists with official custom icon
desktopPath = WshShell.SpecialFolders("Desktop")
shortcutPath = desktopPath & "\CommitMaster Admin.lnk"
If Not fso.FileExists(shortcutPath) Then
    On Error Resume Next
    Set oLink = WshShell.CreateShortcut(shortcutPath)
    oLink.TargetPath = "wscript.exe"
    oLink.Arguments = """" & WScript.ScriptFullName & """"
    oLink.WorkingDirectory = currentDir
    oLink.Description = "CommitMaster Admin Portal"
    If fso.FileExists(currentDir & "\icon.ico") Then
        oLink.IconLocation = currentDir & "\icon.ico, 0"
    End If
    oLink.Save
    On Error GoTo 0
End If

' Determine best Python executable
pyExe = "pythonw.exe"
If fso.FileExists("C:\Python314\pythonw.exe") Then
    pyExe = "C:\Python314\pythonw.exe"
ElseIf fso.FileExists(WshShell.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe")) Then
    pyExe = WshShell.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe")
End If

scriptPath = currentDir & "\admin_app.py"
cmdLine = """" & pyExe & """ """ & scriptPath & """"
WshShell.Run cmdLine, 0, False




