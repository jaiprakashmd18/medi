"""Subjects, tutor, quizzes, revision, progress, dashboard and export routes."""
from __future__ import annotations

import io
import json
import zipfile
from collections import Counter
from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.errors import AppError, ConflictError, NotFoundError
from app.db.session import get_db
from app.exams.generator import generate_quiz
from app.exams.grader import submit_attempt
from app.models import (Attempt, Conversation, Document, DocumentImage, Flashcard, Message, Quiz, StudySession,
                        Subject, Topic, User, utcnow)
from app.revision.service import due_cards, generate_flashcards, review_card, revision_stats
from app.schemas.api import (AttemptOut, ChatIn, ConversationDetail, ConversationOut, DiagramIn, ExplainIn,
                             FlashcardGenerateIn, FlashcardIn, FlashcardOut, FlashcardPatch, MessageOut,
                             QuestionPublic, QuizDetail, QuizGenerateIn, QuizOut, ReviewIn, SubjectIn, SubjectOut,
                             SubmitIn, TopicIn, TopicOut, TopicPatch)
from app.services import documents as docsvc
from app.services.progress import compute_status
from app.services.subjects import slugify, visible_subjects_query
from app.tutor import engine

router = APIRouter()


# ======================================================================= subjects
@router.get("/subjects", response_model=list[SubjectOut], tags=["subjects"])
def list_subjects(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    dc = docsvc.counts_by_subject(db, user.id)
    tc = docsvc.topic_counts(db, user.id)
    out = []
    for s in db.scalars(visible_subjects_query(user.id).order_by(Subject.is_custom, Subject.id)):
        o = SubjectOut.model_validate(s)
        o.document_count = dc.get(s.id, 0)
        o.topic_count = tc.get(s.id, 0)
        out.append(o)
    return out


@router.post("/subjects", response_model=SubjectOut, status_code=201, tags=["subjects"])
def create_subject(body: SubjectIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    slug = slugify(body.name)
    exists = db.scalar(visible_subjects_query(user.id).where(Subject.slug == slug))
    if exists:
        raise ConflictError(f"A subject named '{exists.name}' already exists.")
    s = Subject(user_id=user.id, name=body.name.strip(), slug=slug, description=body.description, color=body.color,
                is_custom=True)
    db.add(s)
    db.commit()
    return s


@router.delete("/subjects/{subject_id}", status_code=204, tags=["subjects"])
def delete_subject(subject_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    s = db.get(Subject, subject_id)
    if s is None or s.user_id != user.id:
        raise NotFoundError("Custom subject not found (built-in subjects cannot be deleted).")
    db.delete(s)
    db.commit()


@router.get("/topics", response_model=list[TopicOut], tags=["subjects"])
def list_topics(subject_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = select(Topic).where(Topic.user_id == user.id)
    if subject_id is not None:
        q = q.where(Topic.subject_id == subject_id)
    return list(db.scalars(q.order_by(Topic.name)))


@router.post("/topics", response_model=TopicOut, status_code=201, tags=["subjects"])
def create_topic(body: TopicIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if body.subject_id is not None:
        subj = db.get(Subject, body.subject_id)
        if subj is None or subj.user_id not in (None, user.id):
            raise NotFoundError("Subject not found.")
    if body.parent_id is not None:
        parent = db.get(Topic, body.parent_id)
        if parent is None or parent.user_id != user.id:
            raise NotFoundError("Parent topic not found.")
    t = Topic(user_id=user.id, subject_id=body.subject_id, parent_id=body.parent_id, name=body.name.strip())
    db.add(t)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise ConflictError("That topic already exists.")
    return t


@router.patch("/topics/{topic_id}", response_model=TopicOut, tags=["subjects"])
def patch_topic(topic_id: int, body: TopicPatch, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    t = db.get(Topic, topic_id)
    if t is None or t.user_id != user.id:
        raise NotFoundError("Topic not found.")
    if body.name:
        t.name = body.name
    if body.status:
        t.status = body.status
        t.status_manual = True
        t.last_studied_at = utcnow()
    db.commit()
    return t


@router.delete("/topics/{topic_id}", status_code=204, tags=["subjects"])
def delete_topic(topic_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    t = db.get(Topic, topic_id)
    if t is None or t.user_id != user.id:
        raise NotFoundError("Topic not found.")
    db.delete(t)
    db.commit()


# ======================================================================= tutor
def _message_out(m: Message) -> MessageOut:
    return MessageOut.model_validate(m)


@router.post("/tutor/chat/stream", tags=["tutor"])
def chat_stream(body: ChatIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    prep = engine.prepare(db, user, engine.TutorRequest(**body.model_dump()))
    uid = user.id
    return StreamingResponse(engine.sse(engine.stream_events(uid, prep)), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _run_blocking(db: Session, user: User, req: engine.TutorRequest):
    prep = engine.prepare(db, user, req)
    done = None
    for ev in engine.stream_events(user.id, prep):
        if ev["event"] in ("done", "error"):
            done = ev
    assert done is not None
    db.expire_all()
    msg = db.get(Message, done["data"]["message_id"])
    payload = {"conversation_id": prep.conversation_id, "message": _message_out(msg).model_dump(mode="json"),
               "routing": prep.selection.reason, "retrieval_note": prep.retrieval.note}
    if done["event"] == "error":
        return JSONResponse(status_code=502, content={"error": {"code": done["data"]["code"],
                                                                "message": done["data"]["message"]}, **payload})
    return payload


@router.post("/tutor/chat", tags=["tutor"])
def chat(body: ChatIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _run_blocking(db, user, engine.TutorRequest(**body.model_dump()))


@router.post("/tutor/explain", tags=["tutor"])
def explain(body: ExplainIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    req = engine.TutorRequest(message=body.message, conversation_id=body.conversation_id,
                              teaching_level=body.teaching_level, action=body.action,
                              document_ids=[body.document_id], page_number=body.page_number)
    return _run_blocking(db, user, req)


@router.post("/tutor/diagram", tags=["tutor"])
def diagram(body: DiagramIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return engine.explain_diagram(db, user, body.image_id, body.teaching_level, body.question)


@router.get("/tutor/history", response_model=list[ConversationOut], tags=["tutor"])
def history(document_id: str | None = None, limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db),
            user: User = Depends(get_current_user)):
    q = select(Conversation).where(Conversation.user_id == user.id)
    if document_id:
        q = q.where(Conversation.document_id == document_id)
    convs = list(db.scalars(q.order_by(Conversation.updated_at.desc()).limit(limit)))
    counts = dict(db.execute(select(Message.conversation_id, func.count()).where(
        Message.conversation_id.in_([c.id for c in convs])).group_by(Message.conversation_id)).all())
    out = []
    for c in convs:
        o = ConversationOut.model_validate(c)
        o.message_count = counts.get(c.id, 0)
        out.append(o)
    return out


@router.get("/tutor/conversations/{conversation_id}", response_model=ConversationDetail, tags=["tutor"])
def conversation(conversation_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    c = db.get(Conversation, conversation_id)
    if c is None or c.user_id != user.id:
        raise NotFoundError("Conversation not found.")
    o = ConversationDetail.model_validate(c)
    o.message_count = len(c.messages)
    return o


@router.delete("/tutor/conversations/{conversation_id}", status_code=204, tags=["tutor"])
def delete_conversation(conversation_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    c = db.get(Conversation, conversation_id)
    if c is None or c.user_id != user.id:
        raise NotFoundError("Conversation not found.")
    db.delete(c)
    db.commit()


# ======================================================================= quizzes
def _quiz_out(db: Session, q: Quiz) -> dict:
    attempts = list(q.attempts)
    data = QuizOut.model_validate(q).model_dump()
    data["question_count"] = len(q.questions)
    data["attempt_count"] = len(attempts)
    data["best_percent"] = max((round(100 * a.score / a.max_score, 1) for a in attempts if a.max_score), default=None)
    return data


def _attempt_out(a: Attempt) -> AttemptOut:
    o = AttemptOut.model_validate(a)
    o.percent = round(100 * a.score / a.max_score, 1) if a.max_score else 0
    o.weak_topics = [t["topic"] for t in a.topic_breakdown if t.get("weak")]
    recs = []
    for t in o.weak_topics:
        recs.append(f"Revise '{t}': re-read the cited pages, ask the AI tutor to explain it simply, then review the "
                    "flashcards created from your mistakes.")
    if not recs and o.percent >= 80:
        recs.append("Strong result. Try a harder difficulty or written/viva questions on the same material.")
    elif not recs:
        recs.append("Review the explanations for questions you missed and retry the quiz in a few days.")
    o.recommendations = recs
    return o


@router.post("/quizzes/generate", status_code=201, tags=["exams"])
def quiz_generate(body: QuizGenerateIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    quiz = generate_quiz(db, user, document_ids=body.document_ids, subject_id=body.subject_id, topic=body.topic,
                         difficulty=body.difficulty, num_questions=body.num_questions,
                         question_types=list(body.question_types), title=body.title)
    return _quiz_detail(db, quiz)


def _quiz_detail(db: Session, quiz: Quiz) -> dict:
    data = _quiz_out(db, quiz)
    qs = []
    for q in quiz.questions:
        p = QuestionPublic.model_validate(q)
        if q.image_id:
            img = db.get(DocumentImage, q.image_id)
            if img:
                p.image_url = f"/api/documents/{img.document_id}/images/{img.id}/file"
        qs.append(p.model_dump())
    data["questions"] = qs
    return QuizDetail(**data).model_dump(mode="json")


@router.get("/quizzes", response_model=list[QuizOut], tags=["exams"])
def quizzes(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [_quiz_out(db, q) for q in db.scalars(select(Quiz).where(Quiz.user_id == user.id)
                                                 .order_by(Quiz.created_at.desc()))]


@router.get("/quizzes/{quiz_id}", tags=["exams"])
def quiz_get(quiz_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.get(Quiz, quiz_id)
    if q is None or q.user_id != user.id:
        raise NotFoundError("Quiz not found.")
    return _quiz_detail(db, q)


@router.delete("/quizzes/{quiz_id}", status_code=204, tags=["exams"])
def quiz_delete(quiz_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.get(Quiz, quiz_id)
    if q is None or q.user_id != user.id:
        raise NotFoundError("Quiz not found.")
    db.delete(q)
    db.commit()


@router.post("/quizzes/{quiz_id}/submit", response_model=AttemptOut, tags=["exams"])
def quiz_submit(quiz_id: str, body: SubmitIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _attempt_out(submit_attempt(db, user, quiz_id, body.answers, body.duration_seconds))


@router.get("/quizzes/{quiz_id}/results", tags=["exams"])
def quiz_results(quiz_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.get(Quiz, quiz_id)
    if q is None or q.user_id != user.id:
        raise NotFoundError("Quiz not found.")
    attempts = sorted(q.attempts, key=lambda a: a.submitted_at, reverse=True)
    return {"quiz": _quiz_out(db, q), "questions": [{"index": x.index, "type": x.type, "prompt": x.prompt,
                                                     "options": x.options} for x in q.questions],
            "attempts": [_attempt_out(a).model_dump(mode="json") for a in attempts]}


# ======================================================================= revision
@router.post("/revision/generate", status_code=201, tags=["revision"])
def revision_generate(body: FlashcardGenerateIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cards, warnings, provider, model = generate_flashcards(db, user, document_ids=body.document_ids,
                                                           subject_id=body.subject_id, topic=body.topic,
                                                           count=body.count)
    return {"cards": [FlashcardOut.model_validate(c).model_dump(mode="json") for c in cards], "warnings": warnings,
            "provider": provider, "model": model}


@router.get("/revision", tags=["revision"])
def revision(limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    weak = list(db.scalars(select(Topic).where(Topic.user_id == user.id, Topic.status == "needs_revision")
                           .order_by(Topic.last_studied_at.desc()).limit(10)))
    return {"stats": revision_stats(db, user.id),
            "due": [FlashcardOut.model_validate(c).model_dump(mode="json") for c in due_cards(db, user.id, limit)],
            "weak_topics": [TopicOut.model_validate(t).model_dump(mode="json") for t in weak]}


@router.get("/revision/cards", response_model=list[FlashcardOut], tags=["revision"])
def cards(topic: str | None = None, document_id: str | None = None, db: Session = Depends(get_db),
          user: User = Depends(get_current_user)):
    q = select(Flashcard).where(Flashcard.user_id == user.id)
    if topic:
        q = q.where(Flashcard.topic == topic)
    if document_id:
        q = q.where(Flashcard.document_id == document_id)
    return list(db.scalars(q.order_by(Flashcard.created_at.desc())))


@router.post("/revision/cards", response_model=FlashcardOut, status_code=201, tags=["revision"])
def create_card(body: FlashcardIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if body.document_id:
        docsvc.get_owned(db, user, body.document_id)
    c = Flashcard(user_id=user.id, origin="manual", **body.model_dump())
    db.add(c)
    db.commit()
    return c


@router.patch("/revision/cards/{card_id}", response_model=FlashcardOut, tags=["revision"])
def patch_card(card_id: int, body: FlashcardPatch, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    c = db.get(Flashcard, card_id)
    if c is None or c.user_id != user.id:
        raise NotFoundError("Flashcard not found.")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    db.commit()
    return c


@router.delete("/revision/cards/{card_id}", status_code=204, tags=["revision"])
def delete_card(card_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    c = db.get(Flashcard, card_id)
    if c is None or c.user_id != user.id:
        raise NotFoundError("Flashcard not found.")
    db.delete(c)
    db.commit()


@router.post("/revision/cards/{card_id}/review", response_model=FlashcardOut, tags=["revision"])
def review(card_id: int, body: ReviewIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return review_card(db, user, card_id, body.rating)


# ======================================================================= progress
def _sessions(db: Session, user_id: str, limit: int):
    rows = list(db.scalars(select(StudySession).where(StudySession.user_id == user_id)
                           .order_by(StudySession.last_activity_at.desc()).limit(limit)))
    return [{"id": s.id, "kind": s.kind, "title": s.title, "document_id": s.document_id,
             "conversation_id": s.conversation_id, "quiz_id": s.quiz_id, "started_at": s.started_at,
             "last_activity_at": s.last_activity_at, "activity_count": s.activity_count} for s in rows]


@router.get("/progress", tags=["progress"])
def progress(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    topics = list(db.scalars(select(Topic).where(Topic.user_id == user.id)))
    for t in topics:  # apply time decay for display
        if not t.status_manual:
            t.status = compute_status(t)
    db.commit()
    status_counts = Counter(t.status for t in topics)
    attempts = list(db.scalars(select(Attempt).where(Attempt.user_id == user.id).order_by(Attempt.submitted_at)))
    subjects = {s.id: s.name for s in db.scalars(visible_subjects_query(user.id))}
    by_subject: dict[str, dict] = {}
    for t in topics:
        name = subjects.get(t.subject_id, "Unassigned") if t.subject_id else "Unassigned"
        b = by_subject.setdefault(name, {"subject": name, "topics": 0, "answered": 0, "correct": 0})
        b["topics"] += 1
        b["answered"] += t.questions_answered
        b["correct"] += t.questions_correct
    for b in by_subject.values():
        b["accuracy"] = round(100 * b["correct"] / b["answered"]) if b["answered"] else None
    now = utcnow()
    days = []
    sessions = list(db.scalars(select(StudySession).where(StudySession.user_id == user.id,
                                                          StudySession.started_at >= now - timedelta(days=30))))
    for i in range(29, -1, -1):
        day = (now - timedelta(days=i)).date()
        n = sum(s.activity_count for s in sessions if (s.started_at.date() if s.started_at else None) == day)
        days.append({"date": day.isoformat(), "activities": n})
    return {
        "disclaimer": "Progress reflects study activity and quiz accuracy on your own materials. It is not a measure "
                      "of clinical competence.",
        "topic_status": {s: status_counts.get(s, 0) for s in
                         ("not_studied", "learning", "needs_revision", "understood", "mastered")},
        "topics": [TopicOut.model_validate(t).model_dump(mode="json") for t in
                   sorted(topics, key=lambda t: (t.status != "needs_revision", t.name.lower()))],
        "subjects": sorted(by_subject.values(), key=lambda b: b["subject"]),
        "quiz_history": [{"quiz_id": a.quiz_id, "submitted_at": a.submitted_at,
                          "percent": round(100 * a.score / a.max_score, 1) if a.max_score else 0,
                          "questions": int(a.max_score)} for a in attempts[-50:]],
        "activity_30d": days,
        "recent_sessions": _sessions(db, user.id, 20),
        "revision": revision_stats(db, user.id),
        "totals": {"documents": db.scalar(select(func.count()).select_from(Document).where(Document.user_id == user.id)),
                   "conversations": db.scalar(select(func.count()).select_from(Conversation).where(Conversation.user_id == user.id)),
                   "quiz_attempts": len(attempts)},
    }


@router.get("/dashboard", tags=["progress"])
def dashboard(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    recent_docs = list(db.scalars(select(Document).where(Document.user_id == user.id)
                                  .order_by(Document.created_at.desc()).limit(6)))
    continue_docs = list(db.scalars(select(Document).where(Document.user_id == user.id,
                                                           Document.last_opened_at.is_not(None))
                                    .order_by(Document.last_opened_at.desc()).limit(3)))
    convs = list(db.scalars(select(Conversation).where(Conversation.user_id == user.id)
                            .order_by(Conversation.updated_at.desc()).limit(4)))
    topics = list(db.scalars(select(Topic).where(Topic.user_id == user.id)))
    return {"user": {"display_name": user.display_name},
            "recent_documents": [docsvc.serialize(d) for d in recent_docs],
            "continue_learning": [docsvc.serialize(d) for d in continue_docs],
            "recent_conversations": [{"id": c.id, "title": c.title, "updated_at": c.updated_at,
                                      "document_id": c.document_id} for c in convs],
            "recent_sessions": _sessions(db, user.id, 6),
            "revision": revision_stats(db, user.id),
            "topic_status": dict(Counter(t.status for t in topics)),
            "subject_counts": {str(k): v for k, v in docsvc.counts_by_subject(db, user.id).items() if k}}


# ======================================================================= export
@router.get("/export", tags=["privacy"])
def export(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Export all of the user's learning data as JSON inside a ZIP (original files not included)."""
    def rows(model, *where):
        out = []
        for r in db.scalars(select(model).where(*where)):
            out.append({c.name: getattr(r, c.name) for c in r.__table__.columns if c.name != "password_hash"})
        return out

    convs = rows(Conversation, Conversation.user_id == user.id)
    conv_ids = [c["id"] for c in convs]
    quiz_rows = rows(Quiz, Quiz.user_id == user.id)
    from app.models import Citation, Question

    data = {
        "exported_at": utcnow(), "user": {"id": user.id, "email": user.email, "display_name": user.display_name},
        "documents": rows(Document, Document.user_id == user.id),
        "subjects": rows(Subject, Subject.user_id == user.id),
        "topics": rows(Topic, Topic.user_id == user.id),
        "conversations": convs,
        "messages": rows(Message, Message.conversation_id.in_(conv_ids)),
        "citations": rows(Citation, Citation.message_id.in_(select(Message.id).where(Message.conversation_id.in_(conv_ids)))),
        "quizzes": quiz_rows,
        "questions": rows(Question, Question.quiz_id.in_([q["id"] for q in quiz_rows])),
        "attempts": rows(Attempt, Attempt.user_id == user.id),
        "flashcards": rows(Flashcard, Flashcard.user_id == user.id),
        "study_sessions": rows(StudySession, StudySession.user_id == user.id),
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("medi-genius-export.json", json.dumps(data, default=str, indent=2))
        z.writestr("README.txt", "MEDI-GENIUS data export. Original uploaded files are not included; download them "
                                 "individually from My Library.\n")
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/zip",
                             headers={"Content-Disposition": 'attachment; filename="medi-genius-export.zip"'})


@router.delete("/account/data", tags=["privacy"])
def delete_all_data(confirm: str = Query(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Securely delete all documents (files, vectors) and learning data for the current user."""
    if confirm != "DELETE":
        raise AppError("Pass confirm=DELETE to erase all of your data.", code="confirmation_required")
    for d in list(db.scalars(select(Document).where(Document.user_id == user.id))):
        docsvc.delete_document(db, user, d.id)
    for model in (Conversation, Quiz, Flashcard, Topic, StudySession, Attempt):
        for r in list(db.scalars(select(model).where(model.user_id == user.id))):
            db.delete(r)
    for s in list(db.scalars(select(Subject).where(Subject.user_id == user.id))):
        db.delete(s)
    db.commit()
    return {"ok": True}
