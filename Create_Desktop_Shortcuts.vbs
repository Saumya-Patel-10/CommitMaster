' CommitMaster — Create Desktop Shortcuts for Admin and User Apps
Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
currentDir = fso.GetParentFolderName(WScript.ScriptFullName)
desktopPath = WshShell.SpecialFolders("Desktop")
iconPath = currentDir & "\icon.ico"

' 1. CommitMaster Admin App Shortcut
adminLinkPath = desktopPath & "\CommitMaster Admin.lnk"
Set oLinkAdmin = WshShell.CreateShortcut(adminLinkPath)
oLinkAdmin.TargetPath = "wscript.exe"
oLinkAdmin.Arguments = """" & currentDir & "\Launch_Admin_App.vbs"""
oLinkAdmin.WorkingDirectory = currentDir
oLinkAdmin.Description = "CommitMaster Admin Portal — Saumya's Private Workspace"
If fso.FileExists(iconPath) Then
    oLinkAdmin.IconLocation = iconPath & ", 0"
End If
oLinkAdmin.Save

' 2. CommitMaster User App Shortcut
userLinkPath = desktopPath & "\CommitMaster.lnk"
Set oLinkUser = WshShell.CreateShortcut(userLinkPath)
oLinkUser.TargetPath = "wscript.exe"
oLinkUser.Arguments = """" & currentDir & "\Launch_CommitMaster.vbs"""
oLinkUser.WorkingDirectory = currentDir
oLinkUser.Description = "CommitMaster Desktop Application"
If fso.FileExists(iconPath) Then
    oLinkUser.IconLocation = iconPath & ", 0"
End If
oLinkUser.Save

WshShell.Popup "Desktop shortcuts created successfully!" & vbCrLf & vbCrLf & _
               "• CommitMaster Admin" & vbCrLf & _
               "• CommitMaster (User App)" & vbCrLf & vbCrLf & _
               "Both shortcuts have been pinned to your Windows Desktop with the official CommitMaster icon.", _
               5, "CommitMaster Desktop Integration", 64
