# Verbatim installer for Windows: Start Menu shortcut + autostart.
param([string]$Shortcut = "Ctrl+Space")

$ErrorActionPreference = "Stop"
$AppDir = "$env:LOCALAPPDATA\Programs\Verbatim"
$Exe = "$AppDir\verbatim.exe"
$StartMenu = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs"
$ShortcutPath = "$StartMenu\Verbatim.lnk"
$AutostartKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"

Write-Host "Installing Verbatim" -Foreground Cyan
Write-Host "----------------"

New-Item -ItemType Directory -Force -Path $AppDir | Out-Null
if (Test-Path "$PSScriptRoot\verbatim.exe") {
    Copy-Item "$PSScriptRoot\verbatim.exe" $Exe -Force
    Write-Host "  [OK] verbatim.exe copied to $Exe"
} elseif (Test-Path "$PSScriptRoot\verbatim.py") {
    Write-Host "  [!] verbatim.exe not found next to install.ps1; run 'pyinstaller verbatim.spec' first."
} else {
    Write-Host "  [!] No verbatim.exe or verbatim.py found here."
    exit 1
}

$Ws = New-Object -ComObject WScript.Shell
$lnk = $Ws.CreateShortcut($ShortcutPath)
$lnk.TargetPath = $Exe
$lnk.WorkingDirectory = $AppDir
$lnk.IconLocation = "$Exe,0"
$lnk.Save()
Write-Host "  [OK] Start Menu shortcut created"

$existing = Get-ItemProperty -Path $AutostartKey -Name "Verbatim" -ErrorAction SilentlyContinue
if (-not $existing) {
    New-ItemProperty -Path $AutostartKey -Name "Verbatim" -Value $Exe -PropertyType String | Out-Null
    Write-Host "  [OK] Autostart entry added"
} else {
    Set-ItemProperty -Path $AutostartKey -Name "Verbatim" -Value $Exe
    Write-Host "  [OK] Autostart entry updated"
}

Write-Host ""
Write-Host "  Done. Start it from the Start Menu, or run verbatim.exe directly." -Foreground Green
Write-Host "  The settings window opens on first run; add your Gemini or OpenRouter keys."
