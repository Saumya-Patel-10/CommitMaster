' CommitMaster — Create Desktop Shortcuts for Admin and User Apps
Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
currentDir = fso.GetParentFolderName(WScript.ScriptFullName)
desktopPath = WshShell.SpecialFolders("Desktop")
adminIconPath = currentDir & "\icon_admin.ico"
userIconPath = currentDir & "\icon_user.ico"
fallbackIcon = currentDir & "\icon.ico"

' 1. CommitMaster Admin App Shortcut
adminLinkPath = desktopPath & "\CommitMaster Admin.lnk"
Set oLinkAdmin = WshShell.CreateShortcut(adminLinkPath)
oLinkAdmin.TargetPath = "wscript.exe"
oLinkAdmin.Arguments = """" & currentDir & "\Launch_Admin_App.vbs"""
oLinkAdmin.WorkingDirectory = currentDir
oLinkAdmin.Description = "CommitMaster Admin Portal — Saumya's Private Workspace"
If fso.FileExists(adminIconPath) Then
    oLinkAdmin.IconLocation = adminIconPath & ", 0"
ElseIf fso.FileExists(fallbackIcon) Then
    oLinkAdmin.IconLocation = fallbackIcon & ", 0"
End If
oLinkAdmin.Save

' 2. CommitMaster User App Shortcut
userLinkPath = desktopPath & "\CommitMaster.lnk"
Set oLinkUser = WshShell.CreateShortcut(userLinkPath)
oLinkUser.TargetPath = "wscript.exe"
oLinkUser.Arguments = """" & currentDir & "\Launch_CommitMaster.vbs"""
oLinkUser.WorkingDirectory = currentDir
oLinkUser.Description = "CommitMaster Desktop Application"
If fso.FileExists(userIconPath) Then
    oLinkUser.IconLocation = userIconPath & ", 0"
ElseIf fso.FileExists(fallbackIcon) Then
    oLinkUser.IconLocation = fallbackIcon & ", 0"
End If
oLinkUser.Save

WshShell.Popup "Desktop shortcuts created successfully!" & vbCrLf & vbCrLf & _
               "• CommitMaster Admin" & vbCrLf & _
               "• CommitMaster (User App)" & vbCrLf & vbCrLf & _
               "Both shortcuts have been pinned to your Windows Desktop with the official CommitMaster icon.", _
               5, "CommitMaster Desktop Integration", 64
