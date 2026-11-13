# Acceptance report

Verification environment: Linux container, Python 3.13, Node 22, Tesseract 5.3.4, LibreOffice, Chromium (Playwright).
Windows was not available; the Windows path is covered by the PowerShell scripts and Windows-specific handling but has
not yet been executed on Windows.

## Automated results (2026-11-13, branch `feature/nvidia-reranker`)

| Suite | Result |
|---|---|
| Backend pytest | **84 passed** (50 core + 34 NVIDIA reranking) |
| Frontend vitest | **10 passed** |
| TypeScript strict typecheck | pass |
| Next.js production build | pass |
| Playwright e2e (`scripts/run-e2e.sh`) | **2 passed** + restart persistence check OK |

## MVP acceptance criteria

| # | Criterion | Verified by | Status |
|---|---|---|---|
| 1 | Open MEDI-GENIUS locally | e2e against `next start` + backend | ✅ (Linux; Windows scripts not executed) |
| 2 | Upload a medical PDF | e2e, `test_pdf_processing` | ✅ |
| 3 | Upload a medical PowerPoint | e2e, `test_pptx_processing` | ✅ |
| 4 | See extracted pages and slides | e2e outline + extracted view (text, tables, speaker notes) | ✅ |
| 5 | View the original document | e2e page render; PPTX via LibreOffice; original download | ✅ |
| 6 | Ask questions about the document | e2e streaming tutor | ✅ |
| 7 | Detailed medical explanations | provider code paths verified; quality depends on the configured model | ⚠️ note A |
| 8 | Beginner and advanced levels | e2e levels 1 and 3; tests check level guidance in the prompt | ✅ |
| 9 | Accurate page/slide citations | e2e citation → viewer jumps to page; tests verify only real sources become citations | ✅ |
| 10 | Follow-up questions | e2e + tests verify history is sent | ✅ |
| 11 | Generate MCQs | e2e + tests (unsupported/malformed questions rejected) | ✅ |
| 12 | Submit answers, get explanations | e2e results with explanations, supporting pages, weak areas | ✅ |
| 13 | Save progress | e2e progress and revision pages | ✅ |
| 14 | Restart without data loss | `run-e2e.sh` restart check; tests re-open the vector index | ✅ |

**Note A.** No Anthropic key, NVIDIA key or Ollama model was available, and no paid API calls were made. AI behaviour
was verified with test doubles: the official Anthropic SDK path against a local fake Messages API, the Ollama provider
over real HTTP against a fake Ollama server, and NVIDIA reranking against a fake NVIDIA endpoint. Answer quality and
NVIDIA ranking quality must be confirmed with real credentials (`backend/scripts/eval_reranker.py --nvidia`).

## Known limitations

* Without LibreOffice, PPTX/DOCX are shown as extracted content, not pixel-exact slides.
* Without Tesseract, scanned pages are marked *partial* with a warning.
* DOCX is cited by **section** (split at Heading 1/2), as it has no fixed pages.
* PDF table extraction is heuristic; complex tables may lose spacing.
* Voice uses the browser Web Speech API (best in Chrome/Edge).
* AI-generated illustrations and 3D anatomy are not implemented.
