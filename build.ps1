param([string]$Python = "python", [switch]$Cuda, [switch]$CpuOnly)

$ErrorActionPreference = "Stop"
$ExpectedFfmpegVersion = "8.1.1-essentials_build-www.gyan.dev"
$ExpectedFfmpegSha256 = "228D7A8556258DE907FDB55F36850078EBC7680B84EC30D84EA02E99BEC1D1EB"
$Ffmpeg = Join-Path $PSScriptRoot "ffmpeg.exe"
Set-Location -LiteralPath $PSScriptRoot

if ($Cuda -and $CpuOnly) { throw 'Choose CUDA or CPU-only, not both.' }
if (-not $CpuOnly) {
    # Standard deliveries include CUDA libraries; the driver stays external.
    & $Python -m pip install -r (Join-Path $PSScriptRoot 'requirements-cuda.txt')
    if ($LASTEXITCODE -ne 0) { throw 'CUDA runtime installation failed.' }
    & $Python -c "import cuda_runtime; missing = cuda_runtime.missing_libraries(); assert not missing, missing"
    if ($LASTEXITCODE -ne 0) { throw 'CUDA runtime DLL verification failed.' }
}

if (-not (Test-Path -LiteralPath $Ffmpeg)) {
    throw "ffmpeg.exe is missing from the project root."
}
$VersionLine = (& $Ffmpeg -version 2>&1 | Select-Object -First 1)
if ($VersionLine -notlike "ffmpeg version $ExpectedFfmpegVersion*") {
    throw "ffmpeg.exe version mismatch. Expected $ExpectedFfmpegVersion, got: $VersionLine"
}
$ActualHash = (Get-FileHash -LiteralPath $Ffmpeg -Algorithm SHA256).Hash
if ($ActualHash -ne $ExpectedFfmpegSha256) {
    throw "ffmpeg.exe hash mismatch. Expected $ExpectedFfmpegSha256, got $ActualHash."
}
$AppVersion = (& $Python -c "from brand import BRAND; print(BRAND.version)").Trim()
if ($LASTEXITCODE -ne 0 -or $AppVersion -notmatch '^\d+\.\d+\.\d+$') {
    throw "Could not read a valid WordArc version from brand.py."
}

& (Join-Path $PSScriptRoot "check.ps1") -Python $Python -Audit
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# Some Windows extraction/scanner paths leave PyInstaller's generated cache
# read-only. Clear that attribute only inside this project's disposable work dir.
$PyInstallerWork = Join-Path $PSScriptRoot "build\wordarc-$AppVersion"
if (Test-Path -LiteralPath $PyInstallerWork) {
    Get-ChildItem -LiteralPath $PyInstallerWork -Recurse -Force | ForEach-Object {
        $_.Attributes = $_.Attributes -band (-bnot [IO.FileAttributes]::ReadOnly)
    }
    $WorkItem = Get-Item -LiteralPath $PyInstallerWork -Force
    $WorkItem.Attributes = $WorkItem.Attributes -band (-bnot [IO.FileAttributes]::ReadOnly)
}

& $Python (Join-Path $PSScriptRoot "tools\build_brand_assets.py")
if ($LASTEXITCODE -ne 0) { throw "Brand asset generation failed." }
& $Python -m PyInstaller --clean --noconfirm --workpath $PyInstallerWork `
    (Join-Path $PSScriptRoot "wordarc.spec")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$RawExe = Join-Path $PSScriptRoot "dist\wordarc.exe"
if (-not (Test-Path -LiteralPath $RawExe)) {
    throw "Expected dist\wordarc.exe was not produced."
}
$VersionedName = "WordArc-$AppVersion.exe"
$VersionedExe = Join-Path $PSScriptRoot "dist\$VersionedName"
Move-Item -LiteralPath $RawExe -Destination $VersionedExe -Force
$LauncherName = "WordArc-$AppVersion.bat"
$LauncherPath = Join-Path $PSScriptRoot "dist\$LauncherName"
$Launcher = "@echo off`r`nsetlocal`r`n" +
    "cd /d `"%~dp0`"`r`n" +
    "start `"WordArc $AppVersion`" `"%~dp0$VersionedName`" %*`r`n"
[IO.File]::WriteAllText($LauncherPath, $Launcher, [Text.UTF8Encoding]::new($false))
$VerificationArgs = @()
if (-not $CpuOnly) { $VerificationArgs = @('--cuda') }
& $Python (Join-Path $PSScriptRoot "tools\verify_release_package.py") @VerificationArgs
if ($LASTEXITCODE -ne 0) { throw "Release package verification failed." }
Write-Host "Build completed: dist\$VersionedName + $LauncherName" -ForegroundColor Green
