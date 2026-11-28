# Madrasa & School Admin System - Windows starter (PowerShell).
# From the "Madrasa Admin Project" folder:  .\start.ps1
# If PowerShell blocks the script, run once:
#   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
# or:  powershell -ExecutionPolicy Bypass -File .\start.ps1
# On the first start: creates the "venv" folder with py and installs the pinned packages.
# See HowToSetup.md, section 2.
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$venvPython = Join-Path $PSScriptRoot "venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $venvPython)) {
    if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
        Write-Error "The Python launcher 'py' was not found. Install Python 3.11 or newer from https://www.python.org/downloads/ and run this script again."
        exit 1
    }
    Write-Host "Creating the virtual environment with py ..."
    py -3 -m venv venv
    if ($LASTEXITCODE -ne 0) { Write-Error "Could not create the virtual environment. See HowToSetup.md, Troubleshooting."; exit 1 }
}

& $venvPython -c "import uvicorn, fastapi, sqlalchemy" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing the pinned packages from requirements.lock ..."
    & $venvPython -m pip install --disable-pip-version-check --require-hashes -r requirements.lock
    if ($LASTEXITCODE -ne 0) { Write-Error "Package installation failed. Check your internet connection and try again."; exit 1 }
}

& $venvPython main.py
