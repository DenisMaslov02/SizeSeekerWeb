# Builds dist\SizeSeekerWeb\ (PyInstaller) and dist\SizeSeekerWeb-Setup-<version>.exe (Inno Setup).
# Usage (from the repo root):  powershell -ExecutionPolicy Bypass -File packaging\build.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$python = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }
$version = & $python -c "import sizeseekerweb; print(sizeseekerweb.__version__)"
if ($LASTEXITCODE -ne 0) { throw "could not read version - is the package installed (pip install -e .[dev])?" }
Write-Host "Building SizeSeekerWeb $version"

& $python -m PyInstaller packaging\sizeseekerweb.spec --noconfirm --clean --distpath dist --workpath build
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$iscc = @(
    (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source,
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup (ISCC.exe) not found - install it with: winget install JRSoftware.InnoSetup" }

& $iscc "/DAppVersion=$version" packaging\installer.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
Write-Host "Done: dist\SizeSeekerWeb-Setup-$version.exe"
