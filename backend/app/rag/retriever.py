"""Hybrid retrieval: semantic (vector) search re-ranked with lexical overlap.

Results always carry document title + page/slide number + section, taken
from the database (never generated), so citations cannot be invented.
"""
from __future__ import annotations

import logging
import math
import re
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Chunk, Document, UserSettings

from . import nvidia_reranker
from .vectorstore import get_vector_store

log = logging.getLogger(__name__)

STOP = set("""a an the of and or to in on for with by is are was were be been as at from that this these those it its
which what how why when where who whom into than then also can may might do does did not no yes about explain describe
tell me please give list""".split())


def tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9][a-z0-9\-]+", text.lower()) if t not in STOP and len(t) > 1]


@dataclass
class RetrievedChunk:
    chunk_id: str
    document_id: str
    document_title: str
    page_number: int
    page_kind: str
    section: str | None
    kind: str
    text: str
    score: float
    semantic: float
    lexical: float
    suspicious: bool = False
    image_id: int | None = None
    # Raw NVIDIA logit when reranked. Ordering signal only: never used for sufficiency
    # and not comparable with `score` (the calibrated local hybrid score).
    rerank_score: float | None = None


@dataclass
class RetrievalResult:
    query: str
    chunks: list[RetrievedChunk] = field(default_factory=list)
    sufficient: bool = False
    note: str = ""
    ranker: str = "local"  # "local" (hybrid) or "nvidia"
    rerank_note: str = ""  # why NVIDIA was not used / fell back (no secrets)

    @property
    def best_score(self) -> float:
        return max((c.score for c in self.chunks), default=0.0)


def page_kind_for(file_type: str) -> str:
    return {"pptx": "slide", "docx": "section", "image": "image"}.get(file_type, "page")


def _lexical(query_tokens: list[str], text: str) -> float:
    if not query_tokens:
        return 0.0
    toks = Counter(tokenize(text))
    if not toks:
        return 0.0
    q = set(query_tokens)
    hit = sum(1 for t in q if t in toks)
    tf = sum(math.log1p(toks[t]) for t in q if t in toks)
    return min(1.0, 0.75 * hit / len(q) + 0.25 * min(1.0, tf / (len(q) * 1.5)))


def retrieve(db: Session, user_id: str, query: str, *, document_ids: list[str] | None = None,
             subject_id: int | None = None, top_k: int | None = None,
             focus_pages: list[tuple[str, int]] | None = None,
             rerank: bool | None = None) -> RetrievalResult:
    """Retrieve the user's most relevant passages.

    ``rerank``: None = use NVIDIA reranking only if this user's settings allow it (default);
    False = local hybrid ranking only. There is deliberately no way to bypass consent.
    """
    s = get_settings()
    top_k = top_k or s.retrieval_top_k
    result = RetrievalResult(query=query)

    # Scope: resolve allowed document ids (user-owned, ready/partial).
    q = select(Document.id).where(Document.user_id == user_id, Document.status.in_(("ready", "partial")))
    if document_ids:
        q = q.where(Document.id.in_(document_ids))
    if subject_id is not None:
        q = q.where(Document.subject_id == subject_id)
    allowed = list(db.scalars(q))
    if not allowed:
        result.note = "No processed documents are available in the selected scope."
        return result

    where: dict = {"user_id": user_id}
    if document_ids or subject_id is not None:
        where = {"$and": [{"user_id": user_id}, {"document_id": {"$in": allowed}}]}

    candidates: dict[str, float] = {}
    for cid, sim in get_vector_store().query(query, n=top_k * 4, where=where):
        candidates[cid] = sim

    # Always consider chunks from the page the student is looking at.
    focus_ids: set[str] = set()
    for doc_id, page in focus_pages or []:
        if doc_id in allowed:
            for c in db.scalars(select(Chunk).where(Chunk.document_id == doc_id, Chunk.page_number == page)):
                focus_ids.add(c.id)
                candidates.setdefault(c.id, 0.0)

    if not candidates:
        result.note = "No relevant passages were found in your documents."
        return result

    rows = db.execute(select(Chunk, Document.title, Document.file_type)
                      .join(Document, Document.id == Chunk.document_id)
                      .where(Chunk.id.in_(list(candidates)), Chunk.user_id == user_id,
                             Chunk.document_id.in_(allowed))).all()
    qt = tokenize(query)
    scored: list[RetrievedChunk] = []
    for chunk, title, ftype in rows:
        sem = max(0.0, candidates.get(chunk.id, 0.0))
        lex = _lexical(qt, (chunk.section or "") + " " + chunk.text)
        score = 0.7 * sem + 0.3 * lex
        if chunk.id in focus_ids:
            score = max(score, 0.45) + 0.1  # page in view is relevant context
        scored.append(RetrievedChunk(
            chunk_id=chunk.id, document_id=chunk.document_id, document_title=title,
            page_number=chunk.page_number, page_kind=page_kind_for(ftype), section=chunk.section,
            kind=chunk.kind, text=chunk.text, score=round(score, 4), semantic=round(sem, 4),
            lexical=round(lex, 4), suspicious=chunk.suspicious, image_id=chunk.image_id))
    scored.sort(key=lambda c: c.score, reverse=True)
    # De-duplicate near-identical texts and keep the eligible pool. Eligibility (the local
    # relevance threshold) is decided BEFORE any reranking, so a reranker can reorder
    # authorized, locally-relevant candidates but never promote filtered-out passages.
    seen: set[str] = set()
    pool: list[RetrievedChunk] = []
    for c in scored:
        key = re.sub(r"\W+", "", c.text.lower())[:200]
        if key in seen:
            continue
        seen.add(key)
        if c.score >= s.retrieval_min_score * 0.6 or c.chunk_id in focus_ids:
            pool.append(c)

    final = pool[:top_k]
    if rerank is not False and len(pool) > 1:
        final = _maybe_rerank(db, user_id, query, pool, top_k, focus_ids, result)
    result.chunks = final
    # Sufficiency uses the calibrated LOCAL scores of the passages actually selected,
    # independent of which ranker ordered them.
    result.sufficient = bool(final) and result.best_score >= s.retrieval_min_score
    if not final:
        result.note = "No sufficiently relevant passages were found in your documents."
    elif not result.sufficient:
        result.note = "Only weakly related passages were found; the documents may not cover this topic."
    return result


def _maybe_rerank(db: Session, user_id: str, query: str, pool: list[RetrievedChunk], top_k: int,
                  focus_ids: set[str], result: RetrievalResult) -> list[RetrievedChunk]:
    """Reorder the authorized candidate pool with NVIDIA; fall back to local order on any problem."""
    s = get_settings()
    local = pool[:top_k]
    st = db.get(UserSettings, user_id)
    allowed, reason = nvidia_reranker.rerank_allowed(st.ai_mode if st else None,
                                                     st.nvidia_consent if st else False)
    if not allowed:
        result.rerank_note = {"no_consent": "NVIDIA reranking not used: no consent given.",
                              "local_only": "NVIDIA reranking not used: local-only mode.",
                              "not_configured": "", "disabled": ""}.get(reason, "")
        return local

    # Candidates sent to NVIDIA: at most NVIDIA_RERANK_MAX_CANDIDATES in total (the cap on
    # outgoing document text), page-in-view chunks first, then the best local candidates.
    # Anything beyond the cap is not sent and is only used locally (appended after the
    # reranked passages).
    cap = max(1, s.nvidia_rerank_max_candidates)
    focus = [c for c in pool if c.chunk_id in focus_ids][:cap]
    focus_set = {c.chunk_id for c in focus}
    cands = focus + [c for c in pool if c.chunk_id not in focus_set][: cap - len(focus)]
    cands.sort(key=lambda c: c.score, reverse=True)  # keep local order for unranked fallback
    sent_ids = {c.chunk_id for c in cands}
    local_rest = [c for c in pool if c.chunk_id not in sent_ids]
    try:
        scores = nvidia_reranker.rerank(query, [c.text for c in cands])
    except nvidia_reranker.RerankUnavailable as exc:
        log.info("NVIDIA rerank fallback (%s)", exc.code)
        result.rerank_note = f"{exc.reason} Used local ranking."
        return local

    ordered: list[RetrievedChunk] = []
    for r in scores:
        c = cands[r.index]
        c.rerank_score = round(r.logit, 4)
        ordered.append(c)
    ranked_ids = {c.chunk_id for c in ordered}
    ordered += [c for c in cands if c.chunk_id not in ranked_ids]  # unranked: keep local order
    ordered += local_rest  # beyond the outgoing cap: local order, never sent to NVIDIA

    final = ordered[:top_k]
    # Page-focus guarantee: the page the student is viewing stays in context.
    missing = [c for c in ordered[top_k:] if c.chunk_id in focus_ids]
    for m in missing:
        for i in range(len(final) - 1, -1, -1):
            if final[i].chunk_id not in focus_ids:
                final[i] = m
                break
    pos = {c.chunk_id: i for i, c in enumerate(ordered)}
    final.sort(key=lambda c: pos[c.chunk_id])
    result.ranker = "nvidia"
    return final
