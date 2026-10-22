<#
.SYNOPSIS
    Builds Peachy standalone executable for Windows.

.DESCRIPTION
    1. Creates a clean Python virtual environment (.venv_build)
    2. Installs pinned dependencies from requirements.txt and requirements-dev.txt
    3. Runs pytest automated test suite (aborts if any test fails)
    4. Generates multi-resolution icon resources\peachy.ico from resources\sparkle.svg
    5. Packages application with PyInstaller in ONEDIR mode (dist\Peachy\Peachy.exe)

.WHY ONEDIR INSTEAD OF ONEFILE
    - Faster Startup: In onedir mode, binaries and Qt libraries are pre-extracted on disk,
      eliminating the 2-4 second decompression penalty every time Peachy starts.
    - Antivirus Resilience: Windows Defender and third-party AV scanners frequently flag
      temporary extraction of DLLs from onefile executables into %TEMP% as suspicious heuristic activity.
    - Modular Updates: Resource files, icons, and dynamic libraries remain directly inspectable and replaceable.
#>

[CmdletBinding()]
param(
    [switch]$SkipTests = $false,
    [switch]$SkipVenv = $false
)

$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Magenta
Write-Host " PEACHY DESKTOP SCREEN ASSISTANT: BUILD PROCESS (DAY 6)" -ForegroundColor Magenta
Write-Host "==========================================================" -ForegroundColor Magenta

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
if (-not $RootDir) { $RootDir = Get-Location }
Set-Location $RootDir

# Resolve Python executable
$PythonExe = "python.exe"
$KnownPython = "C:\Users\TANAY\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\python.exe"
if (Test-Path $KnownPython) {
    $PythonExe = $KnownPython
}

$VenvDir = Join-Path $RootDir ".venv_build"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

if (-not $SkipVenv) {
    Write-Host "[1/5] Creating clean build venv at $VenvDir..." -ForegroundColor Cyan
    if (Test-Path $VenvDir) {
        Remove-Item -Recurse -Force $VenvDir
    }
    & $PythonExe -m venv $VenvDir
    
    Write-Host "[2/5] Installing pinned dependencies..." -ForegroundColor Cyan
    & $VenvPython -m pip install --upgrade pip --quiet
    & $VenvPython -m pip install -r requirements-dev.txt --quiet
} else {
    Write-Host "[1/5] Reusing existing environment..." -ForegroundColor Yellow
    if (-not (Test-Path $VenvPython)) {
        $VenvPython = $PythonExe
    }
}

if (-not $SkipTests) {
    Write-Host "[3/5] Running automated pytest test suite..." -ForegroundColor Cyan
    & $VenvPython -m pytest -q
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Build aborted: Pytest suite failed with exit code $LASTEXITCODE."
        exit $LASTEXITCODE
    }
    Write-Host "  -> All unit and integration tests passed!" -ForegroundColor Green
}

Write-Host "[4/5] Generating multi-resolution icon (peachy.ico)..." -ForegroundColor Cyan
& $VenvPython scripts/generate_ico.py

Write-Host "[5/5] Building standalone executable with PyInstaller (onedir mode)..." -ForegroundColor Cyan
& $VenvPython -m PyInstaller Peachy.spec --noconfirm --clean

# Ensure resources are also copied adjacent to Peachy.exe for maximum compatibility
$DistResources = Join-Path $RootDir "dist\Peachy\resources"
Copy-Item -Recurse -Force (Join-Path $RootDir "resources") $DistResources

$DistExe = Join-Path $RootDir "dist\Peachy\Peachy.exe"
if (Test-Path $DistExe) {
    $ExeSize = (Get-Item $DistExe).Length / 1MB
    Write-Host ""
    Write-Host "==========================================================" -ForegroundColor Green
    Write-Host " BUILD SUCCESSFUL!" -ForegroundColor Green
    Write-Host " Standalone Executable: $DistExe ($("{0:N2}" -f $ExeSize) MB)" -ForegroundColor Green
    Write-Host " Mode: onedir (windowed, zero console)" -ForegroundColor Green
    Write-Host "==========================================================" -ForegroundColor Green
} else {
    Write-Error "Build failed: $DistExe not found."
    exit 1
}
