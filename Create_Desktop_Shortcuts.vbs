' CommitMaster — Create Desktop Shortcuts for Admin and User Apps
Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
currentDir = fso.GetParentFolderName(WScript.ScriptFullName)
adminIconPath = currentDir & "\icon_admin.ico"
userIconPath = currentDir & "\icon_user.ico"
fallbackIcon = currentDir & "\icon.ico"

' Detect all desktop paths (standard and OneDrive)
Dim desktopPaths(2)
desktopPaths(0) = WshShell.SpecialFolders("Desktop")
desktopPaths(1) = WshShell.ExpandEnvironmentStrings("%USERPROFILE%\OneDrive\Desktop")
desktopPaths(2) = WshShell.ExpandEnvironmentStrings("%USERPROFILE%\Desktop")

For Each dPath In desktopPaths
    If dPath <> "" And fso.FolderExists(dPath) Then
        ' 1. CommitMaster Admin App Shortcut
        adminLinkPath = dPath & "\CommitMaster Admin.lnk"
        On Error Resume Next
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
        On Error GoTo 0

        ' 2. CommitMaster Main App Shortcut
        userLinkPath = dPath & "\CommitMaster.lnk"
        On Error Resume Next
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
        On Error GoTo 0
    End If
Next

WshShell.Popup "Desktop shortcuts created successfully!" & vbCrLf & vbCrLf & _
               "• CommitMaster Admin" & vbCrLf & _
               "• CommitMaster" & vbCrLf & vbCrLf & _
               "Both shortcuts are now active on your Windows Desktop.", _
               4, "CommitMaster Desktop Integration", 64
