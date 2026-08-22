# WordArc installer for Windows: Start Menu shortcut + autostart.
$ErrorActionPreference = "Stop"
$AppDir = "$env:LOCALAPPDATA\Programs\WordArc"
$StartMenu = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs"
$ShortcutPath = "$StartMenu\WordArc.lnk"
$LegacyShortcut = "$StartMenu\Verbatim.lnk"
$AutostartKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"

Write-Host "Installing WordArc" -Foreground Cyan
New-Item -ItemType Directory -Path $AppDir -Force | Out-Null
$Packages = @(Get-ChildItem -LiteralPath $PSScriptRoot -File |
    Where-Object { $_.Name -match '^WordArc-\d+\.\d+\.\d+\.exe$' })
if ($Packages.Count -ne 1) {
    throw "Expected exactly one WordArc-X.Y.Z.exe next to install.ps1."
}
$Package = $Packages[0]
$Exe = Join-Path $AppDir $Package.Name
Copy-Item -LiteralPath $Package.FullName -Destination $Exe -Force

$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $Exe
$Shortcut.WorkingDirectory = $AppDir
$Shortcut.IconLocation = "$Exe,0"
$Shortcut.Save()

New-ItemProperty -Path $AutostartKey -Name "WordArc" -Value $Exe -PropertyType String -Force | Out-Null
# Remove only obsolete launch points after WordArc launch points exist.
# Legacy settings and recordings deliberately remain available as a rollback copy.
Remove-ItemProperty -Path $AutostartKey -Name "Verbatim" -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $LegacyShortcut -Force -ErrorAction SilentlyContinue

Write-Host "WordArc installed. Start it from the Start Menu or run $($Package.Name)." -ForegroundColor Green
