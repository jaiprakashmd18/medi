"""Optional second-stage reranking with NVIDIA Nemotron 3.5 Rerank 8B.

Pipeline position:
    ChromaDB + local MiniLM (candidate retrieval, authorization-filtered)
    -> local hybrid score (semantic + lexical)          [always computed]
    -> NVIDIA rerank of the authorized candidate pool   [only when allowed]
    -> top-k passages in reranked order

Privacy contract (enforced by :func:`rerank_allowed` and the caller):
  * runs only if NVIDIA_API_KEY is configured, NVIDIA_RERANK_ENABLED is true,
    the user's AI mode is not ``local_only``, and the user has given (and not
    revoked) NVIDIA-specific consent;
  * only the query text and the candidate passage *texts* are sent - never
    chunk/document ids, titles, file names, user ids or other metadata;
  * passages and query are length-capped (NVIDIA_RERANK_MAX_PASSAGE_CHARS /
    NVIDIA_RERANK_MAX_QUERY_CHARS).

Reliability contract: any failure (no key, timeout, network error, 401/403,
429, 5xx, malformed body) raises :class:`RerankUnavailable`; the retriever then
keeps the local hybrid order. Repeated failures put the reranker in a short
cool-down so a broken endpoint does not add latency to every question.

Scores: NVIDIA returns raw *logits* - unbounded, can be negative, and only
comparable within a single query. They are used for ORDERING only and are
never mixed with, or substituted for, the calibrated local scores that decide
whether the documents contain sufficient evidence.

API format (NVIDIA hosted retrieval / NIM reranking):
    POST {NVIDIA_RERANK_URL}
    {"model": "...", "query": {"text": "..."}, "passages": [{"text": "..."}, ...], "truncate": "END"}
    -> {"rankings": [{"index": <int>, "logit": <float>}, ...]}
"""
from __future__ import annotations

import logging
import math
import threading
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import get_settings

log = logging.getLogger(__name__)


class RerankUnavailable(Exception):
    """NVIDIA reranking could not be used for this request (caller falls back)."""

    def __init__(self, reason: str, code: str) -> None:
        super().__init__(reason)
        self.reason = reason
        self.code = code


@dataclass(frozen=True)
class RerankScore:
    index: int  # index into the passages list that was sent
    logit: float


# ------------------------------------------------------------------ cool-down
_lock = threading.Lock()
_cooldown_until = 0.0
_cooldown_code = ""


def _set_cooldown(seconds: float, code: str) -> None:
    global _cooldown_until, _cooldown_code
    with _lock:
        _cooldown_until = max(_cooldown_until, time.monotonic() + seconds)
        _cooldown_code = code


def reset_state() -> None:
    """Clear the cool-down (tests, or after the admin fixes the key)."""
    global _cooldown_until, _cooldown_code
    with _lock:
        _cooldown_until = 0.0
        _cooldown_code = ""


def cooldown_remaining() -> float:
    with _lock:
        return max(0.0, _cooldown_until - time.monotonic())


# ------------------------------------------------------------------ policy
def is_configured() -> bool:
    s = get_settings()
    return bool(s.nvidia_api_key and s.nvidia_api_key.strip()) and s.nvidia_rerank_enabled


def rerank_allowed(ai_mode: str | None, nvidia_consent: bool | None) -> tuple[bool, str]:
    """Return (allowed, reason). Pure policy check, no network."""
    s = get_settings()
    if not s.nvidia_rerank_enabled:
        return False, "disabled"
    if not (s.nvidia_api_key and s.nvidia_api_key.strip()):
        return False, "not_configured"
    if ai_mode == "local_only":
        return False, "local_only"
    if not nvidia_consent:
        return False, "no_consent"
    return True, "ok"


def status() -> dict[str, Any]:
    s = get_settings()
    return {"name": "nvidia_rerank", "model": s.nvidia_rerank_model, "enabled": s.nvidia_rerank_enabled,
            "configured": bool(s.nvidia_api_key and s.nvidia_api_key.strip()),
            "cooldown_seconds": round(cooldown_remaining()), "cooldown_reason": _cooldown_code or None}


# ------------------------------------------------------------------ API call
def _parse(body: Any, n_passages: int) -> list[RerankScore]:
    if not isinstance(body, dict) or not isinstance(body.get("rankings"), list):
        raise RerankUnavailable("NVIDIA returned an unexpected response format.", "malformed")
    out: list[RerankScore] = []
    seen: set[int] = set()
    for item in body["rankings"]:
        if not isinstance(item, dict):
            raise RerankUnavailable("NVIDIA returned a malformed ranking entry.", "malformed")
        idx, logit = item.get("index"), item.get("logit", item.get("score"))
        if isinstance(idx, bool) or not isinstance(idx, int) or not 0 <= idx < n_passages or idx in seen:
            raise RerankUnavailable("NVIDIA returned an invalid passage index.", "malformed")
        if isinstance(logit, bool) or not isinstance(logit, (int, float)) or not math.isfinite(float(logit)):
            raise RerankUnavailable("NVIDIA returned a non-numeric relevance score.", "malformed")
        seen.add(idx)
        out.append(RerankScore(idx, float(logit)))
    if not out:
        raise RerankUnavailable("NVIDIA returned no rankings.", "malformed")
    # Sort ourselves; do not trust the server's ordering.
    out.sort(key=lambda r: r.logit, reverse=True)
    return out


def rerank(query: str, passages: list[str], *, client: httpx.Client | None = None) -> list[RerankScore]:
    """Rerank passage texts for one query. Returns scores in descending relevance.

    Passages the server did not rank are simply absent from the result; the caller
    appends them after the ranked ones in their original (local) order.
    """
    s = get_settings()
    if not passages:
        return []
    if not (s.nvidia_api_key and s.nvidia_api_key.strip()):
        raise RerankUnavailable("NVIDIA API key is not configured.", "not_configured")
    remaining = cooldown_remaining()
    if remaining > 0:
        raise RerankUnavailable(f"NVIDIA reranking paused for {remaining:.0f}s after an earlier error "
                                f"({_cooldown_code}).", "cooldown")

    payload = {
        "model": s.nvidia_rerank_model,
        "query": {"text": query[: s.nvidia_rerank_max_query_chars]},
        "passages": [{"text": p[: s.nvidia_rerank_max_passage_chars]} for p in passages],
        "truncate": "END",
    }
    headers = {"Authorization": f"Bearer {s.nvidia_api_key.strip()}", "Accept": "application/json",
               "Content-Type": "application/json"}
    own_client = client is None
    c = client or httpx.Client(timeout=httpx.Timeout(s.nvidia_rerank_timeout_seconds, connect=5.0))
    try:
        resp = c.post(s.nvidia_rerank_url, json=payload, headers=headers)
    except httpx.TimeoutException as exc:
        _set_cooldown(30, "timeout")
        raise RerankUnavailable("NVIDIA reranking timed out.", "timeout") from exc
    except httpx.HTTPError as exc:
        _set_cooldown(30, "network_error")
        raise RerankUnavailable("Could not reach the NVIDIA reranking API.", "network_error") from exc
    finally:
        if own_client:
            c.close()

    code = resp.status_code
    if code in (401, 403):
        _set_cooldown(600, "invalid_credentials")
        log.warning("NVIDIA rerank rejected the API key (HTTP %s); using local ranking.", code)
        raise RerankUnavailable("The NVIDIA API key was rejected.", "invalid_credentials")
    if code == 429:
        retry = resp.headers.get("retry-after", "")
        wait = float(retry) if retry.replace(".", "", 1).isdigit() else 60.0
        _set_cooldown(min(max(wait, 5.0), 600.0), "rate_limited")
        raise RerankUnavailable("NVIDIA reranking rate limit reached.", "rate_limited")
    if code == 404:
        _set_cooldown(600, "model_unavailable")
        raise RerankUnavailable("NVIDIA reranking endpoint or model not found (check NVIDIA_RERANK_URL).",
                                "model_unavailable")
    if code >= 500:
        _set_cooldown(30, "provider_error")
        raise RerankUnavailable(f"NVIDIA reranking service error (HTTP {code}).", "provider_error")
    if code >= 400:
        raise RerankUnavailable(f"NVIDIA rejected the rerank request (HTTP {code}).", "bad_request")
    try:
        body = resp.json()
    except ValueError as exc:
        raise RerankUnavailable("NVIDIA returned a non-JSON response.", "malformed") from exc
    return _parse(body, len(passages))
