' CommitMaster — Launch Personal Admin App without console window
Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
currentDir = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = currentDir

' Determine best Python executable (Microsoft-signed to bypass Windows 11 Smart App Control)
pyExe = "pythonw.exe"
If fso.FileExists(WshShell.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe")) Then
    pyExe = WshShell.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe")
ElseIf fso.FileExists("C:\Python314\pythonw.exe") Then
    pyExe = "C:\Python314\pythonw.exe"
End If

scriptPath = currentDir & "\admin_app.py"

' Ensure Desktop shortcut exists with official custom admin icon
desktopPath = WshShell.SpecialFolders("Desktop")
shortcutPath = desktopPath & "\CommitMaster Admin.lnk"
On Error Resume Next
Set oLink = WshShell.CreateShortcut(shortcutPath)
oLink.TargetPath = pyExe
oLink.Arguments = """" & scriptPath & """"
oLink.WorkingDirectory = currentDir
oLink.Description = "CommitMaster Admin Portal"
If fso.FileExists(currentDir & "\icon_admin.ico") Then
    oLink.IconLocation = currentDir & "\icon_admin.ico, 0"
ElseIf fso.FileExists(currentDir & "\icon.ico") Then
    oLink.IconLocation = currentDir & "\icon.ico, 0"
End If
oLink.Save
On Error GoTo 0

' Launch via signed pythonw to bypass Smart App Control
cmdLine = """" & pyExe & """ """ & scriptPath & """"
WshShell.Run cmdLine, 0, False
