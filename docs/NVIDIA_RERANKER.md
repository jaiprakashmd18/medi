# NVIDIA Nemotron reranking

MEDI-GENIUS can optionally use **NVIDIA Nemotron 3.5 Rerank 8B** (`nvidia/nemotron-3.5-rerank-8b`) as a second-stage
reranker for document retrieval. Local search (ChromaDB + MiniLM embeddings + keyword overlap) still finds the
candidate passages. NVIDIA only reorders them so the tutor, quizzes, flashcards and diagram explanations see the most
relevant passages first.

## How it works

```
question
  └─ local retrieval (always, on your computer)
       ChromaDB + MiniLM, restricted to YOUR documents in the selected scope
       + passages of the page you are viewing
  └─ local hybrid score (0.7 semantic + 0.3 keyword) → relevance threshold → eligible pool
  └─ NVIDIA rerank (only if allowed) of the top 24 eligible passages
       → sorted by NVIDIA relevance; page-in-view passages always kept
  └─ top-k passages → numbered sources → answer with validated citations
```

* **Ranking vs. evidence are separate.** NVIDIA returns raw logits (unbounded, can be negative, only comparable within
  one question). They are used only to order passages. The *"Documents only partly cover this"* warning and the
  `sufficient` flag still come from the calibrated local scores of the passages that were selected. A confident
  reranker can neither add a passage that failed the local threshold nor turn weak evidence into "sufficient".
* **Citations are unchanged.** Document ID, title, page/slide number, section and text always come from the
  database. Reranking only changes the order (and therefore the `[n]` numbers). Citation validation (only real source
  numbers become citations) is untouched.
* **Fallback.** Missing key, disabled setting, timeout, network error, 401/403, 402, 404, 429, 5xx or a malformed
  response → the local order is used and the API returns `ranker: "local"` with a `rerank_note`. After an error the
  reranker pauses briefly (timeouts/5xx 30 s, malformed replies 60 s, rate limits per `Retry-After` (5–600 s), bad
  key, no credits or unknown model 10 min) so a broken endpoint doesn't slow every question.
* **Outgoing cap.** At most `NVIDIA_RERANK_MAX_CANDIDATES` (default 24) passages are ever sent per question, page-in-
  view passages first. Any further candidates (e.g. a search asking for 30 results) stay local and follow the
  reranked ones.

## Privacy

| Rule | Implementation |
|---|---|
| No document content without consent | Separate **NVIDIA consent** (`user_settings.nvidia_consent`), off by default. Claude consent does not imply NVIDIA consent. |
| Never in local-only mode | AI mode `local_only` disables reranking even with consent. |
| Revocable | Settings → *Allow NVIDIA reranking* off (or `PUT /api/settings {"nvidia_consent": false}`); takes effect on the next question. |
| Minimum data | Payload is only `model`, `query.text` (≤ 1000 chars) and `passages[].text` (≤ 2000 chars each, ≤ 24 passages). No chunk/document IDs, titles, file names or user identifiers. |
| Only authorized passages | Candidates come from the user-scoped, ownership-checked retrieval pool; another user's passages can never be sent. |
| Key secrecy | `NVIDIA_API_KEY` is read only by the backend, sent only as a bearer header to `NVIDIA_RERANK_URL`, redacted from logs (`nvapi-…` and the literal key), and never returned by any endpoint. |

Note: NVIDIA's hosted API is governed by NVIDIA's own terms (including its API trial terms for free endpoints). Read
them before enabling reranking for real student material.

## Setup

1. Create an API key at <https://build.nvidia.com/nvidia/nemotron-3_5-rerank-8b> (*Get API Key*; keys start with `nvapi-`).
2. Add it to `.env` in the repository root:
   ```
   NVIDIA_API_KEY=nvapi-...
   ```
3. Restart the backend (`scripts\start-backend.ps1`).
4. In the app: **Settings → AI & Privacy → Allow NVIDIA reranking of search results**. The badge shows *Active*.
5. Verify: `GET /api/ai/providers` → `reranker.active_for_you: true`; `GET /api/search?q=...` → `"ranker": "nvidia"`.

**Self-hosted NIM.** Run the NVIDIA reranking NIM container and point `NVIDIA_RERANK_URL` at its ranking endpoint
(e.g. `http://localhost:8001/v1/ranking`). It uses the same request/response format.

## API format used

```
POST {NVIDIA_RERANK_URL}
Authorization: Bearer $NVIDIA_API_KEY
{"model": "nvidia/nemotron-3.5-rerank-8b", "query": {"text": "..."}, "passages": [{"text": "..."}], "truncate": "END"}
→ {"rankings": [{"index": 3, "logit": 2.71}, ...]}
```

This matches NVIDIA's API reference for this model
(<https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3_5-rerank-8b-infer>). Note the model path uses **dots**
(`nemotron-3.5-rerank-8b`); the underscore form returns 404. Limits per the reference: up to 512 passages per
request and a 10,240-token window per query + passage pair (`truncate: END` trims long passages). Errors handled:
401/403 (bad key), 402 (no credits), 404, 422, 429, 5xx. If NVIDIA moves the endpoint, set `NVIDIA_RERANK_URL`; any
other response shape is treated as malformed and falls back to local ranking.

## Evaluation

`backend/tests/data/rerank_eval.json` holds 16 short original study passages (including deliberate distractors) and 18
questions with known answers, 8 of them paraphrases or clinical vignettes.

```
cd backend
python scripts/eval_reranker.py            # local only, offline
python scripts/eval_reranker.py --nvidia   # also NVIDIA (sends only these synthetic passages)
```

Results with the real NVIDIA API (Windows, 2026-11-13, 18 questions):

| Ranker | hit@1 | recall@3 | MRR |
|---|---|---|---|
| Local hybrid (MiniLM) | 0.94 | 1.00 | 0.96 |
| NVIDIA nemotron-3.5-rerank-8b | **1.00** | **1.00** | **1.00** |

NVIDIA ranked the correct passage first for every question, including the one local ranking missed ("Where do the
vessels that supply the heart muscle itself originate?", ranked 3rd locally). The set is small and fairly easy, so
treat this as directional rather than a precise benchmark.

**Latency.** The whole run took 41 s (including loading the local embedding model), roughly 2 s per reranking call
on NVIDIA's free hosted endpoint. With the original 8 s timeout the first (cold-start) call timed out, so the default
is now `NVIDIA_RERANK_TIMEOUT_SECONDS=15`. Expect tutor answers to start ~2 s later when reranking is on; on a timeout
the app answers with local ranking.

**In the app.** Tutor answers show a **"Ranked by NVIDIA"** badge when reranking was used, or
**"NVIDIA unavailable · local ranking"** (with the reason on hover) when it was enabled but failed.
