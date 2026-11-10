<#
  MEDI-GENIUS one-time setup for Windows (PowerShell 5.1+ or PowerShell 7).
  Run from the repository root:   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
#>
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Check($name, $cmd) {
  if (Get-Command $cmd -ErrorAction SilentlyContinue) { Write-Host "  [ok] $name" -ForegroundColor Green; return $true }
  Write-Host "  [--] $name not found" -ForegroundColor Yellow; return $false
}

Write-Host "`nMEDI-GENIUS setup`n" -ForegroundColor Cyan
Write-Host "Checking prerequisites..."
$py = Check "Python 3.11+" "python"
$node = Check "Node.js 20+" "node"
if (-not $py)   { throw "Install Python 3.11+ from https://www.python.org/downloads/ (tick 'Add python.exe to PATH')." }
if (-not $node) { throw "Install Node.js 20 LTS or newer from https://nodejs.org/" }

$tess = (Get-Command tesseract -ErrorAction SilentlyContinue) -or (Test-Path "C:\Program Files\Tesseract-OCR\tesseract.exe")
if ($tess) { Write-Host "  [ok] Tesseract OCR" -ForegroundColor Green }
else { Write-Host "  [--] Tesseract OCR not found (optional, needed for scanned pages): https://github.com/UB-Mannheim/tesseract/wiki" -ForegroundColor Yellow }
$lo = (Get-Command soffice -ErrorAction SilentlyContinue) -or (Test-Path "C:\Program Files\LibreOffice\program\soffice.exe")
if ($lo) { Write-Host "  [ok] LibreOffice" -ForegroundColor Green }
else { Write-Host "  [--] LibreOffice not found (optional, renders PPTX/DOCX slides exactly): https://www.libreoffice.org/" -ForegroundColor Yellow }
Check "Ollama (optional local AI)" "ollama" | Out-Null

Write-Host "`nCreating Python virtual environment (backend\.venv)..."
if (-not (Test-Path "backend\.venv")) { python -m venv backend\.venv }
& backend\.venv\Scripts\python.exe -m pip install --upgrade pip
& backend\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt

Write-Host "`nInstalling frontend dependencies..."
Push-Location frontend
npm install
Pop-Location

if (-not (Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
  Write-Host "`nCreated .env from .env.example - add ANTHROPIC_API_KEY there to enable Claude." -ForegroundColor Cyan
}
if (-not (Test-Path "frontend\.env.local")) { Copy-Item "frontend\.env.example" "frontend\.env.local" }

Write-Host "`nPre-downloading the local embedding model (~80 MB, one time)..."
& backend\.venv\Scripts\python.exe -c "from chromadb.utils.embedding_functions import DefaultEmbeddingFunction as F; F()(['warm up']); print('  [ok] embeddings ready')"

Write-Host "`nSetup complete. Start the app with:  .\scripts\start.ps1`n" -ForegroundColor Green
