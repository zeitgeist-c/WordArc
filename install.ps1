# Dikte installer for Windows: Start Menu shortcut + autostart.
param([string]$Shortcut = "Ctrl+Space")

$ErrorActionPreference = "Stop"
$AppDir = "$env:LOCALAPPDATA\Programs\Dikte"
$Exe = "$AppDir\dikte.exe"
$StartMenu = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs"
$ShortcutPath = "$StartMenu\Dikte.lnk"
$AutostartKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"

Write-Host "Installing Dikte" -Foreground Cyan
Write-Host "----------------"

New-Item -ItemType Directory -Force -Path $AppDir | Out-Null
if (Test-Path "$PSScriptRoot\dikte.exe") {
    Copy-Item "$PSScriptRoot\dikte.exe" $Exe -Force
    Write-Host "  [OK] dikte.exe copied to $Exe"
} elseif (Test-Path "$PSScriptRoot\dikte.py") {
    Write-Host "  [!] dikte.exe not found next to install.ps1; run 'pyinstaller dikte.spec' first."
} else {
    Write-Host "  [!] No dikte.exe or dikte.py found here."
    exit 1
}

$Ws = New-Object -ComObject WScript.Shell
$lnk = $Ws.CreateShortcut($ShortcutPath)
$lnk.TargetPath = $Exe
$lnk.WorkingDirectory = $AppDir
$lnk.IconLocation = "$Exe,0"
$lnk.Save()
Write-Host "  [OK] Start Menu shortcut created"

$existing = Get-ItemProperty -Path $AutostartKey -Name "Dikte" -ErrorAction SilentlyContinue
if (-not $existing) {
    New-ItemProperty -Path $AutostartKey -Name "Dikte" -Value $Exe -PropertyType String | Out-Null
    Write-Host "  [OK] Autostart entry added"
} else {
    Set-ItemProperty -Path $AutostartKey -Name "Dikte" -Value $Exe
    Write-Host "  [OK] Autostart entry updated"
}

Write-Host ""
Write-Host "  Done. Start it from the Start Menu, or run dikte.exe directly." -Foreground Green
Write-Host "  The settings window opens on first run; add your OpenAI and OpenRouter keys."
