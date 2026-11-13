# MEDI-GENIUS

**An AI medical professor that teaches from your own study materials.**

Upload lecture PDFs, PowerPoint slides, Word notes or diagram images. MEDI-GENIUS extracts the text, tables, speaker
notes and diagrams (with OCR for scanned pages), indexes everything locally, and then teaches you — at the level you
choose, with clickable page and slide citations — and builds exams, flashcards and progress tracking around what you
study.

> **Educational use only.** MEDI-GENIUS is not a clinical decision, diagnosis or treatment tool. AI-generated content
> can be wrong; verify important facts against authoritative references.

---

## What works today

| Area | Status |
|---|---|
| Upload PDF / PPTX / DOCX / JPG / PNG (drag-drop, multiple, progress, validation) | ✅ |
| Extraction: text with page/slide numbers, tables, images, PPTX speaker notes, DOCX headings | ✅ |
| Scanned-page detection + Tesseract OCR, OCR of diagram labels | ✅ (needs Tesseract) |
| Processing pipeline with live status, per-page error reporting, retry, resume after restart | ✅ |
| Local embeddings (ONNX MiniLM) + persistent ChromaDB, hybrid semantic + keyword search | ✅ |
| Three-panel workspace: outline · page/slide viewer with zoom · AI tutor (resizable, collapsible, mobile tabs) | ✅ |
| AI tutor: 5 teaching levels, 9 quick actions, streaming, follow-ups, persisted history | ✅ |
| Verifiable citations (document + page/slide + section); fabricated reference numbers are detected and flagged | ✅ |
| Claude (Anthropic API) and Ollama (local) providers, auto / local-only / cloud-only routing, health checks | ✅ |
| Optional NVIDIA Nemotron 3.5 reranking of retrieved passages (separate consent, local fallback) | ✅ — [setup](docs/NVIDIA_RERANKER.md) |
| Explicit consent before any document excerpt goes to the cloud | ✅ |
| Prompt-injection hygiene for document content | ✅ |
| Visual learning: diagram gallery, enlarge, AI diagram explanation (vision), OCR label quiz | ✅ |
| Exams: SBA, multi-select, true/false, fill-in, short, long, viva, diagram ID; evidence-checked; scoring; weak areas | ✅ |
| Revision: flashcards (AI, manual, from quiz mistakes), SM-2 spaced repetition, daily queue | ✅ |
| Progress analytics, topic status, study history | ✅ |
| Voice: read answers aloud (speed, voice, pause/resume), dictate questions, hands-free voice mode | ✅ (browser Web Speech API) |
| Data export, delete-all, optional multi-user accounts | ✅ |
| AI-generated study illustrations, 3D anatomy | ⏳ planned — see [Remaining work](#remaining-work) |

---

## Quick start (Windows)

Prerequisites: **Python 3.11+**, **Node.js 20+**, Git. Recommended: **Tesseract OCR** (for scanned pages) and
**LibreOffice** (to render slides exactly as designed). Optional: **Ollama** for fully local AI.

```powershell
git clone https://github.com/jaiprakashmd18/medi.git
cd medi
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1   # venv, pip, npm, .env, embedding model
.\scripts\start.ps1                                          # opens http://localhost:3000
```

Or start the two servers yourself in two terminals:

```powershell
.\scripts\start-backend.ps1    # http://localhost:8000  (API docs: http://localhost:8000/docs)
.\scripts\start-frontend.ps1   # http://localhost:3000
```

macOS / Linux: `python3 -m venv backend/.venv && backend/.venv/bin/pip install -r backend/requirements-dev.txt`,
`cd frontend && npm install`, then `./scripts/dev.sh`.

### Optional: better search ranking with NVIDIA

Set `NVIDIA_API_KEY` in `.env`, restart the backend, and switch on **Settings → Allow NVIDIA reranking**. Only the
question and the retrieved passage texts are sent, never in local-only mode. See
[docs/NVIDIA_RERANKER.md](docs/NVIDIA_RERANKER.md).

### Turn on the AI

MEDI-GENIUS needs at least one AI provider for teaching, quizzes and flashcards. Everything else (upload, extraction,
OCR, search, the viewer) works without one.

**Option A — Claude (best quality).**
1. Create an API key at <https://console.anthropic.com/> and add billing there.
   **A Claude.ai Pro/Max subscription does not include API credits; API usage is billed separately.**
2. Put it in `.env` (repository root): `ANTHROPIC_API_KEY=sk-ant-...`
3. Restart the backend, open **Settings → AI & Privacy**, and switch on *“Allow sending document excerpts to Claude”*.
   Without that consent no document content is sent to the cloud.

Default models: `claude-opus-5-5` for teaching, exams and diagrams, `claude-haiku-5-5` for simple tasks
(`ANTHROPIC_MODEL`, `ANTHROPIC_FAST_MODEL`, `ANTHROPIC_EFFORT` in `.env`).

**Option B — Ollama (private, free, runs on your PC).**
```powershell
# install from https://ollama.com, then:
ollama pull llama3.1:8b      # text model
ollama pull llava:7b         # optional: diagram (vision) model
```
Choose **Local only** in Settings to keep everything on your machine. Smaller local models give noticeably weaker
explanations and may fail the quiz quality checks more often than Claude.

The top bar always shows which provider and model will answer, and every answer is labelled with the provider and model
that actually produced it.

---

## Using it

1. **My Library** → drop files. Watch extraction → OCR → chunking → embedding → indexing. Subjects are suggested
   automatically (editable).
2. Open a document → the **workspace**: outline on the left, the original page/slide (or the extracted text, tables and
   speaker notes) in the centre, the **AI tutor** on the right. Pick a level 1–5, ask anything, or use quick actions such
   as *Explain simply*, *Mechanism*, *Clinical correlation*, *Test me*. Click a citation chip to jump to that page.
3. **Practice & Exams** → choose documents, topic, difficulty, number and question types → take the exam → see
   explanations with the supporting page, per-topic scores, weak areas and recommendations. Mistakes become flashcards.
4. **Revision Centre** → review due flashcards (Again / Hard / Good / Easy).
5. **Visual Learning** → every extracted diagram; enlarge, get an explanation, or hide the labels and test yourself.
6. **Progress Analytics** → topic statuses, quiz history, activity.

Answers are badged **From your documents**, **Documents only partly cover this**, or **General AI knowledge**, and
extra teaching the AI adds beyond your documents appears under *“Additional explanation (AI-generated)”*.

---

## Tests

```powershell
.\scripts\run-tests.ps1    # backend pytest (49) + frontend typecheck + vitest (10)
.\scripts\run-e2e.ps1      # Playwright acceptance test in a real browser
```
On macOS/Linux: `cd backend && pytest`, `cd frontend && npm test`, and `./scripts/run-e2e.sh` (which also restarts the
backend and verifies data survives).

The automated tests use **test doubles** for AI providers (a fake provider object in pytest and a fake
Ollama-compatible HTTP server in e2e) so they run offline and deterministically. The application itself never uses
canned answers.

---

## Privacy & security

* Documents, the database and the vector index live in `data/` on your computer (git-ignored).
* Extraction, OCR, embeddings and search always run locally.
* Cloud AI is only used with your explicit consent, and then only the retrieved excerpts (plus a diagram you ask about)
  are sent — never whole documents.
* API keys live only in the backend `.env` and are redacted from logs; the browser never sees them.
* Uploads are checked by extension **and** file signature, size-limited, and stored under generated names.
* Document text is treated as untrusted data: it is wrapped and escaped in prompts, and instruction-like passages are flagged.
* Settings → *Export my learning data* and *Delete everything*.

More: [ARCHITECTURE.md](ARCHITECTURE.md) · [DEVELOPMENT.md](DEVELOPMENT.md) · [CHANGELOG.md](CHANGELOG.md) ·
[docs/API.md](docs/API.md) · [docs/ACCEPTANCE.md](docs/ACCEPTANCE.md)

## Remaining work

* AI-generated study illustrations (will be watermarked as AI-generated and kept separate from source diagrams).
* Interactive 3D anatomy with Three.js and licensed anatomy assets.
* Server-side speech (Whisper / neural TTS) for browsers without Web Speech support; barge-in while speaking.
* Live validation of the Claude integration against a real API key (implemented; see [docs/ACCEPTANCE.md](docs/ACCEPTANCE.md)).
* Cloud object storage backend and a packaged Windows installer.
