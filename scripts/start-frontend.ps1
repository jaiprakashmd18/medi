# Starts the Next.js frontend on http://localhost:3000
$Root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $Root "frontend")
npm run dev
