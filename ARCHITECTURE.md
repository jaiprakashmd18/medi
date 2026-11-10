# MEDI-GENIUS architecture

```
┌──────────────────────── Browser (Next.js 15 / React 19 / Tailwind) ─────────────────────────┐
│ Dashboard · Library · Workspace (outline | viewer | tutor) · Tutor · Visual · Exams ·       │
│ Revision · Progress · Settings          Web Speech API (TTS / STT) runs here                 │
└───────────────▲───────────────────────────────▲──────────────────────────────────────────────┘
                │ REST + JSON                   │ SSE (tutor streaming)
┌───────────────┴───────────────────────────────┴──────────── FastAPI (Python) ───────────────┐
│ api/routes   documents · search · images · tutor · quizzes · revision · progress · settings │
│              auth · system(health, providers) · export / delete-all                         │
│ processing/  validation → storage → extract(PDF/PPTX/DOCX/image) → OCR → images → chunk →   │
│              embed → index   (background worker threads, status per stage, resumable)       │
│ rag/         ChromaDB (persistent) + local ONNX MiniLM embeddings; hybrid retriever          │
│ tutor/       Medical Teaching Engine: levels, actions, prompts, citation verification        │
│ exams/       evidence-grounded generator + validator; deterministic/AI/estimate grading      │
│ revision/    flashcard generation, SM-2 scheduler                                            │
│ ai/          provider abstraction: AnthropicProvider (cloud) · OllamaProvider (local) ·      │
│              router (auto / local_only / cloud_only + consent + health)                      │
│ services/    storage abstraction · documents · subjects · progress · activity · users        │
│ db/ models/  SQLAlchemy 2 + Alembic (SQLite default, PostgreSQL-ready)                       │
└──────────┬───────────────────┬───────────────────┬──────────────────────┬────────────────────┘
           │                   │                   │                      │
     data/medigenius.db   data/uploads/…      data/vectors/         Claude API / Ollama
     (metadata)           data/derived/…      (Chroma index)        (only when routed)
```

## Data model

`Subject → Topic → Document → DocumentPage → Chunk / DocumentImage`, plus `Conversation → Message → Citation`,
`Quiz → Question`, `Attempt`, `Flashcard → ReviewLog`, `StudySession`, `User → UserSettings`.

* Every chunk belongs to exactly **one** page/slide/section (chunking never crosses page boundaries), so every
  citation resolves to one location.
* Deleting a document removes its vectors, chunks, pages, images, derived files and original file; citations keep
  their stored title/page text but lose the link.
* Original files, derived files (images, renders, previews) and metadata are kept in separate locations.

## Processing pipeline

| Stage | What happens | Status value |
|---|---|---|
| Validation | extension + magic bytes + size, safe filename | `validating` |
| Storage | original saved under `uploads/<user>/<doc>/original.<ext>` | `stored` |
| Extraction | PyMuPDF / python-pptx / python-docx / Pillow; tables, headings, TOC, notes | `extracting` |
| OCR | pages with < 40 visible characters and images are rendered at 300 dpi and OCR'd | `ocr` |
| Image analysis | embedded images ≥ 64 px saved, de-duplicated, labels OCR'd | `analysing_images` |
| Preview | PPTX/DOCX → PDF via LibreOffice (if installed) for faithful rendering | — |
| Chunking | ~1100-char passages with overlap; tables, notes and diagram text are separate chunks | `chunking` |
| Embeddings / indexing | local MiniLM ONNX → ChromaDB (cosine) | `embedding` / `indexing` |
| Done | `ready`, or `partial` when any page failed/needed unavailable OCR, or `failed` with a message | |

Nothing is silently dropped: skipped tiny/duplicate images, failed pages, low OCR confidence and missing tools are
recorded as page/document warnings and shown in the UI. Failed documents can be retried; documents interrupted by a
restart are re-queued on startup.

## Retrieval and citations

1. Scope = the user's ready documents, optionally narrowed to documents or a subject (authorization is enforced in SQL
   before vector search).
2. Vector search (top-k × 4) + chunks of the page currently viewed.
3. Re-rank: `0.7 · cosine + 0.3 · lexical overlap`; de-duplicate; keep top-k.
4. `sufficient` = best score ≥ `RETRIEVAL_MIN_SCORE`. Otherwise the model is told the sources are weak and must say so.
5. Sources are numbered `[1]…[n]` inside `<sources>` tags. After generation the engine parses the `[n]` markers; only
   numbers that exist are stored as citations (`used_in_answer = true`). Other numbers are reported as
   `invalid_citations` and rendered as warnings — the model cannot create a citation.
6. Citation metadata (document title, page/slide, section, snippet) always comes from the database.

## AI routing

| Task | auto | local_only | cloud_only |
|---|---|---|---|
| extraction, OCR, embeddings, search | local | local | local |
| `simple` | Ollama → Claude* | Ollama | Claude* |
| `explain`, `generate` (quizzes, flashcards, grading) | Claude* → Ollama | Ollama | Claude* |
| `vision` (diagrams) | Claude* → Ollama vision model → text-only fallback (clearly labelled) | Ollama vision | Claude* |

\* only if `ANTHROPIC_API_KEY` is set, the health check passes **and** the user has given cloud consent.

Providers report the model that actually served the request; that value (not the requested one) is stored and shown.
Claude calls use streaming, adaptive thinking, `output_config.effort`, structured JSON outputs for quizzes/flashcards,
and the server-side refusal fallback beta. Errors (auth, billing, rate limits, timeouts, network, unknown model,
refusals) are mapped to clear messages.

## Prompt-injection defence

Document text is never placed in the system prompt. It is wrapped in `<source>` elements whose delimiter-like tags
are escaped, the system prompt states that sources are untrusted data, and chunks that look like instructions are
flagged (`suspicious`) and marked in the prompt and UI. Quiz/flashcard outputs are schema-validated and every item
must reference a real source.

## Frontend

* `src/app` — routes; `src/components` — design system + shell; `src/features` — library, workspace, tutor, exams,
  revision, visual; `src/services/api.ts` — typed client incl. SSE parser and XHR upload progress; `src/hooks` —
  data fetching, app status context, speech; `src/types` — API types.
* The browser talks to the backend directly (`NEXT_PUBLIC_API_URL`, CORS-restricted). No secrets in the frontend.

## Voice architecture

Phase 7 uses the browser's Web Speech API (no extra services): `useSpeechSynthesis` (rate, voice, pause/resume,
sentence chunking, citation stripping) and `useSpeechRecognition` (dictation, interim results). *Voice mode* reads
each answer aloud automatically; pressing the mic stops speech and starts listening (manual interruption). The hooks
isolate the engine, so a server-side STT/TTS provider can be added later without UI changes.
