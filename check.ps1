param(
    [string]$Python = "python",
    [switch]$Audit
)

$ErrorActionPreference = "Stop"
$env:QT_QPA_PLATFORM = "offscreen"

& $Python -m pytest -q
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $Python -m compileall -q .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $Python -c "import api, audio, audio_capture, brand, brand_migration, config, credential_store, diagnostics, filetranscribe, hotkey, i18n, meeting, operation, overlay, paste, settings_ui, startup, theme, trayicon, vad, verbatim, wordarc, worker; print('all imports ok')"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if ($Audit) {
    # requirements-lock.txt contains the complete, exactly pinned runtime set;
    # avoid re-resolving large GUI wheels during every release build.
    & $Python -m pip_audit -r requirements-lock.txt --no-deps --disable-pip `
        --vulnerability-service osv --timeout 15 --progress-spinner off
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $Python -m cyclonedx_py requirements requirements-lock.txt `
        --output-reproducible --output-file sbom.json
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Host "Checks passed." -ForegroundColor Green
