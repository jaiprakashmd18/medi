# Changelog

## Unreleased — NVIDIA Nemotron reranking
- Optional second-stage reranking with `nvidia/nemotron-3.5-rerank-8b` (`backend/app/rag/nvidia_reranker.py`),
  applied to the authorized local candidate pool in `retriever.py`; preserves chunk/document/page/section metadata,
  page-focus passages and citation validation.
- Separate, revocable NVIDIA consent (`user_settings.nvidia_consent`, migration `0002`), disabled in local-only mode,
  Settings toggle, reranker status in `/api/ai/providers`, `ranker`/`rerank_note` in search results and tutor metadata.
- Robust failure handling (timeouts, auth, 404, 429 with Retry-After, 5xx, malformed bodies) with local fallback and
  cool-down; NVIDIA keys redacted from logs.
- Ranking separated from sufficiency: logits only order passages; evidence warnings still use calibrated local scores.
- Evaluation set (18 questions) + `scripts/eval_reranker.py`; 34 new tests (84 backend tests total).

## 0.1.0 — 2026-11-08 — initial MVP

### Phase 1 — Foundation
- FastAPI backend with structured errors, settings via environment, SQLAlchemy 2 models, Alembic migration,
  health check (`/api/health`) and provider status (`/api/ai/providers`).
- Next.js 15 + React 19 + Tailwind frontend with design system, navigation shell and backend connectivity checks.
- Windows PowerShell setup/start/test scripts; VS Code settings.

### Phase 2 — Document intelligence
- Upload of PDF, PPTX, DOCX, JPG/JPEG, PNG with drag-and-drop, multi-file, progress, signature validation, size limit.
- Background pipeline with per-stage status, warnings, retry and resume after restart.
- PDF text/TOC/headings/tables/images, scanned-page detection and Tesseract OCR; PPTX slide text, tables, images and
  speaker notes; DOCX headings, paragraphs, tables, images (split into sections); image OCR.
- LibreOffice-based previews for PPTX/DOCX when available; page rendering with zoom.
- Local subject suggestion, library search (title + full text) and semantic search.

### Phase 3 — AI medical tutor
- Provider abstraction with Claude (Anthropic SDK: streaming, adaptive thinking, effort, structured outputs, refusal
  fallback) and Ollama; auto / local-only / cloud-only routing; explicit cloud consent; health checks; error mapping.
- RAG over ChromaDB with local ONNX embeddings and hybrid re-ranking.
- Teaching engine with 5 levels and 9 quick actions, SSE streaming, persisted conversations, verified citations,
  grounding labels, prompt-injection hygiene.

### Phase 4 — Visual learning
- Diagram gallery, enlargement, diagram explanation (vision model, or clearly labelled text-only fallback),
  OCR label-location quiz on original diagrams.

### Phase 5 — Examinations
- Evidence-grounded generation of 8 question types with validation (support, answer keys, no all/none of the above),
  deterministic, AI and estimated grading, topic breakdown, weak areas, recommendations, citations per question.

### Phase 6 — Revision
- Flashcards (AI from documents, manual, automatic from quiz mistakes), SM-2 scheduling, daily queue, topic status
  tracking, study sessions, progress analytics.

### Phase 7 — Voice
- Browser speech synthesis (rate, voice, pause/resume/stop) and recognition (dictation), hands-free voice mode.

### Phase 8 — Quality
- 49 backend tests, 10 frontend unit tests, Playwright acceptance suite; security review (ownership checks, log
  redaction, consent gating, upload validation); documentation.
