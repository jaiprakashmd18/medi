# End-to-end acceptance tests on Windows. Uses a throw-away data directory and the fake Ollama test server.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Tmp = Join-Path $env:TEMP ("mg-e2e-" + [guid]::NewGuid())
$env:DATA_DIR = "$Tmp\data"; $env:OLLAMA_BASE_URL = "http://127.0.0.1:11500"; $env:ANTHROPIC_API_KEY = ""; $env:PYTHON = "$Root\backend\.venv\Scripts\python.exe"
$py = "$Root\backend\.venv\Scripts\python.exe"
$procs = @()
$procs += Start-Process $py -ArgumentList "$Root\tests\e2e\fake_ollama.py --port 11500" -PassThru -WindowStyle Hidden
$procs += Start-Process $py -ArgumentList "-m uvicorn app.main:app --port 8000" -WorkingDirectory "$Root\backend" -PassThru -WindowStyle Hidden
Push-Location "$Root\frontend"
npx next build | Out-Null
$procs += Start-Process "npx.cmd" -ArgumentList "next start -p 3000" -PassThru -WindowStyle Hidden
Start-Sleep 8
try { npx playwright test } finally { $procs | ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }; Pop-Location }
