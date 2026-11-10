# Starts backend and frontend in two new PowerShell windows, then opens the browser.
$Root = Split-Path -Parent $PSScriptRoot
Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $Root "scripts\start-backend.ps1")
Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $Root "scripts\start-frontend.ps1")
Write-Host "Waiting for MEDI-GENIUS to start..."
for ($i = 0; $i -lt 60; $i++) {
  try { Invoke-WebRequest -UseBasicParsing http://localhost:3000 -TimeoutSec 2 | Out-Null; break } catch { Start-Sleep 2 }
}
Start-Process "http://localhost:3000"
