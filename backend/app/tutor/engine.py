"""Medical Teaching Engine: retrieval-grounded, level-aware tutoring with
verifiable citations and persistent conversations."""
from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import router
from app.ai.base import ChatImage, ChatMessage
from app.ai.router import Selection
from app.core.errors import AIProviderError, AIUnavailableError, AppError, NotFoundError
from app.db.session import session_scope
from app.models import Citation, Conversation, Document, DocumentImage, Message, User, utcnow
from app.rag.retriever import RetrievalResult, RetrievedChunk, page_kind_for, retrieve
from app.services.activity import record_activity
from app.services.storage import get_storage
from app.services.users import get_user_settings

from .prompts import ACTIONS, build_system, build_user_turn

log = logging.getLogger(__name__)

HISTORY_TURNS = 10
CITE_RE = re.compile(r"\[(\d{1,2}(?:\s*[,–-]\s*\d{1,2})*)\]")


@dataclass
class TutorRequest:
    message: str
    conversation_id: str | None = None
    teaching_level: int | None = None
    action: str | None = None
    document_ids: list[str] = field(default_factory=list)
    subject_id: int | None = None
    page_number: int | None = None  # page/slide currently viewed (with a single document)


@dataclass
class Prepared:
    conversation_id: str
    user_message_id: str
    retrieval: RetrievalResult
    selection: Selection
    system: str
    messages: list[ChatMessage]
    level: int
    action: str | None
    document_ids: list[str]


def cited_labels(text: str) -> list[int]:
    labels: list[int] = []
    for m in CITE_RE.finditer(text):
        for part in re.split(r"\s*,\s*", m.group(1)):
            if re.search(r"[–-]", part):
                a, b = [int(x) for x in re.split(r"\s*[–-]\s*", part)[:2]]
                rng = range(min(a, b), max(a, b) + 1) if abs(b - a) < 10 else [a, b]
                labels.extend(rng)
            elif part.strip().isdigit():
                labels.append(int(part))
    out: list[int] = []
    for n in labels:
        if n not in out:
            out.append(n)
    return out


def _strip_citations(text: str) -> str:
    return CITE_RE.sub("", text)


def source_payload(i: int, c: RetrievedChunk) -> dict[str, Any]:
    return {"label": i, "document_id": c.document_id, "document_title": c.document_title,
            "page_number": c.page_number, "page_kind": c.page_kind, "section": c.section,
            "kind": c.kind, "snippet": c.text[:400], "score": c.score, "chunk_id": c.chunk_id}


def _conversation(db: Session, user: User, req: TutorRequest, level: int) -> Conversation:
    if req.conversation_id:
        conv = db.get(Conversation, req.conversation_id)
        if conv is None or conv.user_id != user.id:
            raise NotFoundError("Conversation not found.")
        conv.teaching_level = level
        return conv
    title = re.sub(r"\s+", " ", req.message).strip()[:80] or "New conversation"
    conv = Conversation(user_id=user.id, title=title, teaching_level=level,
                        document_id=req.document_ids[0] if len(req.document_ids) == 1 else None,
                        subject_id=req.subject_id)
    db.add(conv)
    db.flush()
    return conv


def prepare(db: Session, user: User, req: TutorRequest) -> Prepared:
    if not req.message.strip() and not req.action:
        raise AppError("Please type a question.", code="empty_message")
    if req.action and req.action not in ACTIONS:
        raise AppError(f"Unknown action '{req.action}'.", code="bad_action")
    settings = get_user_settings(db, user)
    level = req.teaching_level or settings.default_teaching_level
    if level not in range(1, 6):
        raise AppError("Teaching level must be between 1 and 5.", code="bad_level")

    # validate document scope belongs to user
    for did in req.document_ids:
        d = db.get(Document, did)
        if d is None or d.user_id != user.id:
            raise NotFoundError("Document not found.")

    conv = _conversation(db, user, req, level)
    # carry previous document scope on follow-ups
    doc_ids = list(req.document_ids) or ([conv.document_id] if conv.document_id else [])

    history = list(db.scalars(select(Message).where(Message.conversation_id == conv.id,
                                                    Message.status != "error")
                              .order_by(Message.created_at.desc()).limit(HISTORY_TURNS)))[::-1]

    question = req.message.strip() or (ACTIONS[req.action] if req.action else "")
    # Retrieval query: follow-ups ("explain more", actions) reuse the previous user question for context.
    prev_user = next((m.content for m in reversed(history) if m.role == "user"), "")
    rq = question
    if req.action or len(question.split()) < 6:
        rq = (prev_user + " " + question).strip()

    focus = [(doc_ids[0], req.page_number)] if (len(doc_ids) == 1 and req.page_number) else None
    retrieval = retrieve(db, user.id, rq, document_ids=doc_ids or None, subject_id=req.subject_id, focus_pages=focus)

    page_context = None
    if focus:
        d = db.get(Document, doc_ids[0])
        page_context = f'"{d.title}", {page_kind_for(d.file_type)} {req.page_number}'

    selection = router.select("explain", settings.ai_mode, settings.cloud_consent)

    user_msg = Message(conversation_id=conv.id, role="user", content=question, action=req.action,
                       teaching_level=level)
    db.add(user_msg)
    conv.updated_at = utcnow()
    db.commit()

    msgs: list[ChatMessage] = []
    for m in history:
        content = _strip_citations(m.content) if m.role == "assistant" else m.content
        msgs.append(ChatMessage(role=m.role, content=content))  # type: ignore[arg-type]
    # merge consecutive same-role turns (APIs require alternation)
    msgs.append(ChatMessage(role="user", content=build_user_turn(question, retrieval.chunks, req.action,
                                                                 retrieval.note, page_context)))
    merged: list[ChatMessage] = []
    for m in msgs:
        if merged and merged[-1].role == m.role:
            merged[-1] = ChatMessage(role=m.role, content=merged[-1].content + "\n\n" + m.content)
        else:
            merged.append(m)
    if merged and merged[0].role != "user":
        merged = merged[1:]
    return Prepared(conv.id, user_msg.id, retrieval, selection, build_system(level), merged, level, req.action,
                    doc_ids)


def _grounding(retrieval: RetrievalResult, used: list[int]) -> str:
    if not retrieval.chunks:
        return "general"
    if used:
        return "documents" if retrieval.sufficient else "insufficient"
    return "insufficient" if not retrieval.sufficient else "general"


def finalize(user_id: str, prep: Prepared, text: str, provider: str, model: str, usage: dict, status: str = "complete",
             error: str | None = None) -> dict[str, Any]:
    used = cited_labels(text)
    n = len(prep.retrieval.chunks)
    valid = [u for u in used if 1 <= u <= n]
    invalid = [u for u in used if u not in valid]
    grounding = _grounding(prep.retrieval, valid)
    with session_scope() as db:
        msg = Message(conversation_id=prep.conversation_id, role="assistant", content=text or (error or ""),
                      action=prep.action, teaching_level=prep.level, provider=provider, model=model,
                      grounding=grounding, status=status,
                      meta={"usage": usage, "invalid_citations": invalid, "routing": prep.selection.reason,
                            "retrieval_note": prep.retrieval.note, "error": error})
        db.add(msg)
        db.flush()
        for i, c in enumerate(prep.retrieval.chunks, start=1):
            db.add(Citation(message_id=msg.id, label=i, document_id=c.document_id, chunk_id=c.chunk_id,
                            document_title=c.document_title, page_number=c.page_number, page_kind=c.page_kind,
                            section=c.section, snippet=c.text[:600], score=c.score, used_in_answer=i in valid))
        conv = db.get(Conversation, prep.conversation_id)
        if conv:
            conv.updated_at = utcnow()
        msg_id = msg.id
        record_activity(db, user_id, "tutor", document_id=prep.document_ids[0] if prep.document_ids else None,
                        conversation_id=prep.conversation_id, title=conv.title if conv else "Tutor")
    return {"message_id": msg_id, "grounding": grounding, "used_citations": valid, "invalid_citations": invalid}


def stream_events(user_id: str, prep: Prepared) -> Iterator[dict[str, Any]]:
    sel = prep.selection
    yield {"event": "meta", "data": {
        "conversation_id": prep.conversation_id, "user_message_id": prep.user_message_id,
        "provider": sel.provider.name, "provider_kind": sel.provider.kind, "model": sel.model,
        "routing": sel.reason, "teaching_level": prep.level,
        "sources": [source_payload(i, c) for i, c in enumerate(prep.retrieval.chunks, start=1)],
        "retrieval_sufficient": prep.retrieval.sufficient, "retrieval_note": prep.retrieval.note}}
    parts: list[str] = []
    try:
        result = sel.provider.stream(system=prep.system, messages=prep.messages, model=sel.model)
        for delta in result:
            parts.append(delta)
            yield {"event": "delta", "data": {"text": delta}}
        comp = result.completion
        text = comp.text if comp and comp.text else "".join(parts)
        info = finalize(user_id, prep, text, comp.provider if comp else sel.provider.name,
                        comp.model if comp else sel.model, comp.usage if comp else {},
                        status="partial" if comp and comp.stop_reason == "max_tokens" else "complete")
        yield {"event": "done", "data": {**info, "provider": comp.provider if comp else sel.provider.name,
                                         "model": comp.model if comp else sel.model,
                                         "truncated": bool(comp and comp.stop_reason == "max_tokens")}}
    except (AIProviderError, AIUnavailableError) as exc:
        info = finalize(user_id, prep, "".join(parts), sel.provider.name, sel.model, {}, status="error",
                        error=exc.message)
        yield {"event": "error", "data": {"code": exc.code, "message": exc.message, **info}}
    except Exception as exc:  # pragma: no cover - unexpected
        log.exception("tutor stream failed")
        info = finalize(user_id, prep, "".join(parts), sel.provider.name, sel.model, {}, status="error",
                        error="Unexpected error while generating the answer.")
        yield {"event": "error", "data": {"code": "internal_error", "message": str(exc), **info}}


def sse(events: Iterator[dict[str, Any]]) -> Iterator[str]:
    for ev in events:
        yield f"event: {ev['event']}\ndata: {json.dumps(ev['data'], default=str)}\n\n"


# --------------------------------------------------------------------------- diagrams
DIAGRAM_SYSTEM_EXTRA = """
DIAGRAM RULES
- Describe only what is visible or written in the image/OCR text. If a label or structure is unclear, say it is uncertain
  rather than guessing. Never invent labels that are not present.
- Distinguish: (a) what the source diagram shows, (b) your additional AI-generated teaching.
- Where relevant for anatomy diagrams, structure the explanation (e.g. for the heart: external anatomy, chambers, valves,
  blood flow, coronary circulation, nerve supply, relationships, clinical correlations) but only include parts that the
  diagram or sources support, plus clearly labelled AI teaching.
"""


def explain_diagram(db: Session, user: User, image_id: int, level: int | None, question: str | None) -> dict[str, Any]:
    img = db.get(DocumentImage, image_id)
    if img is None:
        raise NotFoundError("Image not found.")
    doc = db.get(Document, img.document_id)
    if doc is None or doc.user_id != user.id:
        raise NotFoundError("Image not found.")
    st = get_user_settings(db, user)
    level = level or st.default_teaching_level
    vision = True
    try:
        sel = router.select("vision", st.ai_mode, st.cloud_consent)
    except AIUnavailableError as first:
        try:
            sel = router.select("explain", st.ai_mode, st.cloud_consent)
            vision = False
        except AIUnavailableError:
            raise first
    query = (question or "") + " " + (img.ocr_text or "")
    retrieval = retrieve(db, user.id, query.strip() or f"diagram page {img.page_number}", document_ids=[doc.id],
                         focus_pages=[(doc.id, img.page_number)], top_k=6)
    kind = page_kind_for(doc.file_type)
    ask = question or "Explain this diagram in detail for my level."
    context = (f'The diagram is an ORIGINAL image from the student\'s document "{doc.title}", {kind} {img.page_number}.\n'
               f"Text read from the image by OCR (may contain errors): {img.ocr_text or '(none detected)'}\n")
    if not vision:
        context += ("IMPORTANT: you cannot see the image itself. Explain using only the OCR labels and page text, and "
                    "state clearly at the start that the image was not visually analysed.\n")
    user_turn = context + "\n" + build_user_turn(ask, retrieval.chunks, "diagram", retrieval.note, None)
    images = [ChatImage(get_storage().read_bytes(img.path), img.mime_type)] if vision else []
    comp = sel.provider.complete(system=build_system(level) + DIAGRAM_SYSTEM_EXTRA,
                                 messages=[ChatMessage("user", user_turn, images)], model=sel.model)
    img.ai_description = comp.text
    img.ai_provider = comp.provider
    img.ai_model = comp.model
    record_activity(db, user.id, "visual", document_id=doc.id, title=f"Diagram - {doc.title} {kind} {img.page_number}")
    db.commit()
    used = [u for u in cited_labels(comp.text) if 1 <= u <= len(retrieval.chunks)]
    return {"image_id": img.id, "explanation": comp.text, "provider": comp.provider, "model": comp.model,
            "vision_used": vision, "routing": sel.reason,
            "sources": [source_payload(i, c) for i, c in enumerate(retrieval.chunks, start=1)],
            "used_citations": used, "origin": "original",
            "notice": None if vision else "No vision-capable model was available: this explanation is based only on "
                                          "OCR text and page content, not on visual analysis of the image."}
