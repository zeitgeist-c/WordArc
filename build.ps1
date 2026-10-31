param([string]$Python = "python", [switch]$Cuda, [switch]$CpuOnly)

$ErrorActionPreference = "Stop"

# Windows PowerShell 5 + ErrorActionPreference=Stop turns a native command's
# FIRST stderr line into a terminating NativeCommandError whatever the exit
# code — PyInstaller logs INFO to stderr, pip and CUDA checks may warn. The
# exit code is the verdict; stderr only joins the log stream. Same helper
# shape as check.ps1. Returns the command output so callers can capture it.
function Invoke-Gate {
    param([Parameter(Mandatory)][scriptblock]$Gate, [string]$FailMessage)
    $saved = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $out = & $Gate 2>&1
    $code = $LASTEXITCODE
    $ErrorActionPreference = $saved
    $out | ForEach-Object { Write-Output "$_" }
    if ($code -ne 0) {
        if ($FailMessage) { throw $FailMessage }
        exit $code
    }
}

$ExpectedFfmpegVersion = "8.1.1-essentials_build-www.gyan.dev"
$ExpectedFfmpegSha256 = "228D7A8556258DE907FDB55F36850078EBC7680B84EC30D84EA02E99BEC1D1EB"
$Ffmpeg = Join-Path $PSScriptRoot "ffmpeg.exe"
Set-Location -LiteralPath $PSScriptRoot

if ($Cuda -and $CpuOnly) { throw 'Choose CUDA or CPU-only, not both.' }
Invoke-Gate { & $Python -m pip install -r (Join-Path $PSScriptRoot 'requirements-native-build.txt') } 'Vulkan build tool installation failed.'
Invoke-Gate { & $Python (Join-Path $PSScriptRoot 'tools\build_vulkan.py') } 'Vulkan runtime build/verification failed.'
# NOTE: package_vulkan_runtime.py is deliberately not called. runtime.json is
# the canonical pin (v0.10.4 URL + hash); rewriting it on every build turned the
# URL into whatever version was current and produced a 404 (AUD-WORD-002). When
# a new Vulkan build is needed: produce it by hand, upload it to the release,
# and update runtime.json.
if (-not $CpuOnly) {
    # Standard deliveries include CUDA libraries; the driver stays external.
    Invoke-Gate { & $Python -m pip install -r (Join-Path $PSScriptRoot 'requirements-cuda.txt') } 'CUDA runtime installation failed.'
    Invoke-Gate { & $Python -c "import cuda_runtime; missing = cuda_runtime.missing_libraries(); assert not missing, missing" } 'CUDA runtime DLL verification failed.'
}

if (-not (Test-Path -LiteralPath $Ffmpeg)) {
    throw "ffmpeg.exe is missing from the project root."
}
$VersionLine = (Invoke-Gate { & $Ffmpeg -version 2>&1 } | Select-Object -First 1)
if ($VersionLine -notlike "ffmpeg version $ExpectedFfmpegVersion*") {
    throw "ffmpeg.exe version mismatch. Expected $ExpectedFfmpegVersion, got: $VersionLine"
}
$ActualHash = (Get-FileHash -LiteralPath $Ffmpeg -Algorithm SHA256).Hash
if ($ActualHash -ne $ExpectedFfmpegSha256) {
    throw "ffmpeg.exe hash mismatch. Expected $ExpectedFfmpegSha256, got $ActualHash."
}
$AppVersion = (Invoke-Gate { & $Python -c "from brand import BRAND; print(BRAND.version)" } | Select-Object -Last 1)
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

Invoke-Gate { & $Python (Join-Path $PSScriptRoot "tools\build_brand_assets.py") } "Brand asset generation failed."
Invoke-Gate { & $Python (Join-Path $PSScriptRoot "tools\fetch_ema_models.py") } "TTS model vendoring failed."
Invoke-Gate { & $Python (Join-Path $PSScriptRoot "tools\build_update_helper.py") } "Update supervisor build failed."
if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot "tools\vendor\cuda-manifest.json"))) {
    Invoke-Gate { & $Python (Join-Path $PSScriptRoot "tools\build_cuda_libs.py") } "CUDA libs packaging failed."
}
Invoke-Gate { & $Python -m PyInstaller --clean --noconfirm --workpath $PyInstallerWork `
    (Join-Path $PSScriptRoot "wordarc.spec") }

$RawExe = Join-Path $PSScriptRoot "dist\wordarc.exe"
if (-not (Test-Path -LiteralPath $RawExe)) {
    throw "Expected dist\wordarc.exe was not produced."
}
# Fixed inner name: versioned files never pile up in the installed folder, and
# an update overwrites in place.
$InnerDir = Join-Path $PSScriptRoot "dist\inner"
New-Item -ItemType Directory -Path $InnerDir -Force | Out-Null
$InnerExe = Join-Path $InnerDir "WordArc.exe"
Move-Item -LiteralPath $RawExe -Destination $InnerExe -Force
$IsccCandidates = @()
try { $IsccCmd = Get-Command ISCC.exe -ErrorAction Stop; $IsccCandidates += $IsccCmd.Source } catch {}
$IsccCandidates += "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
$IsccCandidates += "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
$IsccCandidates += "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
$Iscc = $IsccCandidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
if (-not $Iscc) {
    throw "Inno Setup 6 (ISCC.exe) was not found. Install it from https://www.innosetup.com/isdl.php or add ISCC.exe to PATH."
}
$env:WORDARC_VERSION = $AppVersion
$VersionNum = ($AppVersion -replace '[^0-9.]', '').Trim('.')
while (($VersionNum.Split('.')).Count -lt 4) { $VersionNum += ".0" }
$env:WORDARC_VERSION_NUM = $VersionNum
Invoke-Gate { & $Iscc (Join-Path $PSScriptRoot "installer\wordarc.iss") } "Inno Setup build failed."
$SetupName = "WordArc-$AppVersion.exe"
$SetupExe = Join-Path $PSScriptRoot "dist\$SetupName"
if (-not (Test-Path -LiteralPath $SetupExe)) {
    throw "Expected dist\$SetupName was not produced."
}
$VerificationArgs = @()
if (-not $CpuOnly) { $VerificationArgs = @('--cuda') }
Invoke-Gate { & $Python (Join-Path $PSScriptRoot "tools\verify_release_package.py") @VerificationArgs } "Release package verification failed."
Write-Host "Build completed: dist\$SetupName (setup)" -ForegroundColor Green
