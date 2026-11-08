#!/usr/bin/env bash
# Runs the end-to-end acceptance suite against a fresh, throw-away data directory.
# Starts: fake Ollama test server (:11500), backend (:8000), production frontend (:3000).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
export DATA_DIR="$TMP/data" OLLAMA_BASE_URL="http://127.0.0.1:11500" ANTHROPIC_API_KEY="" NEXT_TELEMETRY_DISABLED=1
pids=()
cleanup() { for p in "${pids[@]}"; do kill "$p" 2>/dev/null || true; done; rm -rf "$TMP"; }
trap cleanup EXIT
python3 "$ROOT/tests/e2e/fake_ollama.py" --port 11500 & pids+=($!)
(cd "$ROOT/backend" && exec uvicorn app.main:app --port 8000) > "$TMP/backend.log" 2>&1 & pids+=($!)
(cd "$ROOT/frontend" && [ -d .next ] || npx next build >/dev/null) 
(cd "$ROOT/frontend" && exec npx next start -p 3000) > "$TMP/frontend.log" 2>&1 & pids+=($!)
for i in $(seq 1 60); do curl -sf localhost:8000/api/health >/dev/null && curl -sf localhost:3000 >/dev/null && break; sleep 1; done
cd "$ROOT/frontend" && npx playwright test --trace off "$@"
# Restart the backend on the same data directory and verify persistence.
kill "${pids[1]}"; sleep 2
(cd "$ROOT/backend" && exec uvicorn app.main:app --port 8000) > "$TMP/backend2.log" 2>&1 & pids+=($!)
for i in $(seq 1 30); do curl -sf localhost:8000/api/health >/dev/null && break; sleep 1; done
n=$(curl -s localhost:8000/api/documents | python3 -c "import sys,json; print(len(json.load(sys.stdin)))")
c=$(curl -s localhost:8000/api/tutor/history | python3 -c "import sys,json; print(len(json.load(sys.stdin)))")
q=$(curl -s localhost:8000/api/quizzes | python3 -c "import sys,json; print(len(json.load(sys.stdin)))")
echo "After restart: documents=$n conversations=$c quizzes=$q"
[ "$n" -ge 2 ] && [ "$c" -ge 1 ] && [ "$q" -ge 1 ] && echo "PERSISTENCE OK"
