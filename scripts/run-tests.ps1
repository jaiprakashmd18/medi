# Runs backend (pytest) and frontend (vitest + typecheck) test suites.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Push-Location (Join-Path $Root "backend"); & .\.venv\Scripts\python.exe -m pytest -q; $b = $LASTEXITCODE; Pop-Location
Push-Location (Join-Path $Root "frontend"); npm run typecheck; npm test; $f = $LASTEXITCODE; Pop-Location
if ($b -ne 0 -or $f -ne 0) { Write-Host "Tests FAILED" -ForegroundColor Red; exit 1 }
Write-Host "All tests passed" -ForegroundColor Green
