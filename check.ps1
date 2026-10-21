param(
    [string]$Python = "python",
    [switch]$Audit
)

$ErrorActionPreference = "Stop"
$env:QT_QPA_PLATFORM = "offscreen"

# Windows PowerShell 5 + ErrorActionPreference=Stop turns a native command's
# FIRST stderr line into a terminating NativeCommandError, whatever the exit
# code. pip_audit warns, compileall walks .venv (third-party SyntaxWarnings),
# pytest may log to stderr. None of that is a gate failure. Every gate runs
# through this helper: stderr is merged into the stream, the real exit code is
# the verdict.
function Invoke-Gate {
    param([Parameter(Mandatory)][scriptblock]$Gate)
    $saved = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & $Gate 2>&1 | ForEach-Object { Write-Output "$_" }
    $code = $LASTEXITCODE
    $ErrorActionPreference = $saved
    if ($code -ne 0) { exit $code }
}

Invoke-Gate { & $Python -m pytest -q }

Invoke-Gate { & $Python -m compileall -q . }

Invoke-Gate { & $Python -c "import api, audio, audio_capture, brand, brand_migration, config, credential_store, diagnostics, filetranscribe, hotkey, i18n, livespeech, localspeech, meeting, ocr, update, operation, overlay, paste, screenshot_capture, settings_ui, sounds, startup, theme, trayicon, vad, verbatim, wordarc, worker; print('all imports ok')" }

$Iss = Get-Content -LiteralPath (Join-Path $PSScriptRoot "installer\wordarc.iss") -Raw
foreach ($marker in @('PrivilegesRequired=admin', 'CleanOldPortable', 'runasoriginaluser', 'OutputBaseFilename=WordArc-{#AppVersion}', 'GetEnv("WORDARC_VERSION")', 'GetEnv("WORDARC_VERSION_NUM")')) {
    if ($Iss -notmatch [regex]::Escape($marker)) { throw "installer/wordarc.iss marker eksik: $marker" }
}
Write-Host "Installer markers ok." -ForegroundColor Green

if ($Audit) {
    # requirements-lock.txt contains the complete, exactly pinned runtime set;
    # avoid re-resolving large GUI wheels during every release build.
    Invoke-Gate { & $Python -m pip_audit -r requirements-lock.txt --no-deps --disable-pip `
        --vulnerability-service osv --timeout 15 --progress-spinner off }
    Invoke-Gate { & $Python -m cyclonedx_py requirements requirements-lock.txt `
        --output-reproducible --output-file sbom.json }
}

Write-Host "Checks passed." -ForegroundColor Green
