# Public demo starter for Windows PowerShell.
# From the "Madrasa Admin Project" folder:  .\start-demo.ps1
# Then open http://localhost:8000 — landing page, Live Demo, Take the tour.
# For a real school install, use .\start.ps1 instead.
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$env:DEMO_MODE = "true"
$env:SEED_DEMO_DATA = "true"
& (Join-Path $PSScriptRoot "start.ps1")
