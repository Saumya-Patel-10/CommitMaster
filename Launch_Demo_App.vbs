' CommitMaster — Launch the demo app without a console window.
' The shortcut name is "CommitMaster Demo" and does not replace the user shortcut.
Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
currentDir = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = currentDir

desktopPath = WshShell.SpecialFolders("Desktop")
shortcutPath = desktopPath & "\CommitMaster Demo.lnk"
If Not fso.FileExists(shortcutPath) Then
    On Error Resume Next
    Set oLink = WshShell.CreateShortcut(shortcutPath)
    oLink.TargetPath = "wscript.exe"
    oLink.Arguments = """" & WScript.ScriptFullName & """"
    oLink.WorkingDirectory = currentDir
    oLink.Description = "CommitMaster Demo"
    If fso.FileExists(currentDir & "\icon_demo.ico") Then
        oLink.IconLocation = currentDir & "\icon_demo.ico, 0"
    ElseIf fso.FileExists(currentDir & "\assets\icon_demo.ico") Then
        oLink.IconLocation = currentDir & "\assets\icon_demo.ico, 0"
    End If
    oLink.Save
    On Error GoTo 0
End If

demoExe = currentDir & "\dist\CommitMaster-Demo.exe"
If fso.FileExists(currentDir & "\CommitMaster-Demo.exe") Then
    demoExe = currentDir & "\CommitMaster-Demo.exe"
End If

If fso.FileExists(demoExe) Then
    WshShell.Run """" & demoExe & """", 1, False
    WScript.Quit 0
End If

pyExe = "pythonw.exe"
If fso.FileExists(WshShell.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe")) Then
    pyExe = WshShell.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe")
ElseIf fso.FileExists("C:\Python314\pythonw.exe") Then
    pyExe = "C:\Python314\pythonw.exe"
End If

scriptPath = currentDir & "\demo_app.py"
cmdLine = """" & pyExe & """ """ & scriptPath & """"
WshShell.Run cmdLine, 0, False
