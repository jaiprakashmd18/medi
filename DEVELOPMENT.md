# Development guide

## Layout

```
backend/      FastAPI app (app/), Alembic migrations, pytest suite (tests/)
frontend/     Next.js app (src/), vitest unit tests, Playwright e2e (e2e/)
tests/e2e/    fake_ollama.py — Ollama-compatible TEST DOUBLE used by the e2e suite
scripts/      PowerShell (Windows) and bash helpers
docs/         API reference and acceptance report
data/         runtime data (git-ignored): SQLite DB, uploads, derived files, vector index
```

## Environment

All backend configuration is environment-driven (`backend/app/core/config.py`); see `.env.example`. The backend reads
`.env` from the repository root and then `backend/.env`. The frontend only needs `NEXT_PUBLIC_API_URL`
(`frontend/.env.local`).

## Running

```powershell
.\scripts\start-backend.ps1     # uvicorn --reload on :8000
.\scripts\start-frontend.ps1    # next dev on :3000
```

Interactive API docs: <http://localhost:8000/docs>.

## Database migrations

The app runs `alembic upgrade head` on startup. After changing models:

```powershell
cd backend
.\.venv\Scripts\alembic revision --autogenerate -m "describe change"
# review the generated file in alembic/versions, then restart the backend
```

Migrations use batch mode so they work on SQLite; set `DATABASE_URL` for PostgreSQL (install a driver such as
`psycopg[binary]`).

## Tests

| Suite | Command | What it covers |
|---|---|---|
| Backend | `cd backend; pytest` | health, validation, PDF/PPTX/DOCX/PNG extraction, OCR, tables, notes, images, injection flagging, search, deletion cascade, reprocess, corrupted files, routing rules + consent, tutor streaming/citations/follow-ups, diagram explanation, Anthropic error mapping, Ollama provider over real HTTP, quizzes (validation, grading, AI grading fallback), flashcards + SM-2, progress, export, restart persistence, multi-user isolation, log redaction |
| Frontend unit | `cd frontend; npm test` | citation parsing/rendering, SSE parsing, speech text cleanup, utils |
| Types | `cd frontend; npm run typecheck` | strict TypeScript |
| E2E | `scripts/run-e2e.ps1` or `scripts/run-e2e.sh` | the 14 MVP acceptance steps in Chromium, mobile layout, restart persistence (sh) |

Backend tests set `EMBEDDING_BACKEND=hashing` (a deterministic test-only embedder) so they are fast and offline; the
application default is the local ONNX MiniLM model. AI calls in tests go to `FakeProvider` (pytest) or
`tests/e2e/fake_ollama.py` (e2e). These are test doubles only.

## Adding an AI provider

Implement `app.ai.base.LLMProvider` (`health`, `model_for`, `complete`, `stream`), register it in
`app.ai.router.get_provider`, and extend `select()` routing. Report the served model in `Completion.model`.

## Conventions

* API errors: raise `AppError` subclasses → `{"error": {"code", "message", "details"}}`.
* Every query is scoped by `user_id`; resource endpoints call `get_owned(...)`.
* Never log secrets; the logging filter redacts API keys and `access_token` query params.
* Commit messages: imperative summary + body explaining why.
