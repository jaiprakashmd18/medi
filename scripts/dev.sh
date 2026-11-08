#!/usr/bin/env bash
# macOS/Linux convenience: start backend (:8000) and frontend (:3000) together.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
(cd "$ROOT/backend" && exec python3 -m uvicorn app.main:app --port 8000 --reload --reload-dir app) &
BACK=$!
trap 'kill $BACK 2>/dev/null' EXIT
cd "$ROOT/frontend" && npm run dev
