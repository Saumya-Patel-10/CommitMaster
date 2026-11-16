$sh = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath("Desktop")
$pyExe = "$env:LOCALAPPDATA\Programs\Python\Python312\pythonw.exe"
$projectDir = "C:\Data\Saumya\AI-Projects\CommitMaster"

# Also check OneDrive Desktop if applicable
$desktops = @($desktop)
if (Test-Path "$env:USERPROFILE\OneDrive\Desktop") {
    $desktops += "$env:USERPROFILE\OneDrive\Desktop"
}

foreach ($d in ($desktops | Select-Object -Unique)) {
    # 1. CommitMaster (User)
    $scUser = $sh.CreateShortcut("$d\CommitMaster.lnk")
    $scUser.TargetPath = $pyExe
    $scUser.Arguments = "`"$projectDir\main.py`""
    $scUser.WorkingDirectory = $projectDir
    $scUser.Description = "CommitMaster User App"
    $scUser.IconLocation = "$projectDir\icon.ico,0"
    $scUser.Save()

    # 2. CommitMaster Admin
    $scAdmin = $sh.CreateShortcut("$d\CommitMaster Admin.lnk")
    $scAdmin.TargetPath = $pyExe
    $scAdmin.Arguments = "`"$projectDir\admin_app.py`""
    $scAdmin.WorkingDirectory = $projectDir
    $scAdmin.Description = "CommitMaster Admin Portal"
    $scAdmin.IconLocation = "$projectDir\icon_admin.ico,0"
    $scAdmin.Save()

    # 3. CommitMaster Demo
    $scDemo = $sh.CreateShortcut("$d\CommitMaster Demo.lnk")
    $scDemo.TargetPath = $pyExe
    $scDemo.Arguments = "`"$projectDir\demo_app.py`""
    $scDemo.WorkingDirectory = $projectDir
    $scDemo.Description = "CommitMaster Demo Environment"
    $scDemo.IconLocation = "$projectDir\icon_demo.ico,0"
    $scDemo.Save()
}

Write-Output "All 3 Desktop shortcuts created and verified."
