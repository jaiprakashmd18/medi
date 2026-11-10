# Starts the FastAPI backend on http://localhost:8000 (API docs at /docs)
$Root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $Root "backend")
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir app
