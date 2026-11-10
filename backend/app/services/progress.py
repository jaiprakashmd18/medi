"""Topic status tracking. Status reflects study activity and quiz accuracy;
it is a study aid, not a measure of clinical competence."""
from __future__ import annotations

from datetime import timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Topic, utcnow

STATUSES = ["not_studied", "learning", "needs_revision", "understood", "mastered"]


def compute_status(t: Topic) -> str:
    if t.questions_answered == 0:
        return "learning" if t.tutor_messages else "not_studied"
    acc = t.questions_correct / t.questions_answered
    if t.questions_answered < 3:
        return "learning" if acc >= 0.6 else "needs_revision"
    if acc >= 0.9 and t.questions_answered >= 8:
        status = "mastered"
    elif acc >= 0.75:
        status = "understood"
    elif acc < 0.6:
        status = "needs_revision"
    else:
        status = "learning"
    # decay: understood/mastered topics not touched for 30 days need revision
    last = t.last_studied_at
    if last and status in ("understood", "mastered"):
        last = last if last.tzinfo else last.replace(tzinfo=timezone.utc)
        if utcnow() - last > timedelta(days=30):
            status = "needs_revision"
    return status


def get_or_create_topic(db: Session, user_id: str, subject_id: int | None, name: str) -> Topic:
    name = name.strip()[:200] or "General"
    t = db.scalar(select(Topic).where(Topic.user_id == user_id, Topic.subject_id.is_(subject_id) if subject_id is None
                                      else Topic.subject_id == subject_id, Topic.parent_id.is_(None),
                                      Topic.name == name))
    if t is None:
        t = Topic(user_id=user_id, subject_id=subject_id, name=name)
        db.add(t)
        db.flush()
    return t


def update_topic_stats(db: Session, user_id: str, subject_id: int | None, name: str, *, answered: int = 0,
                       correct: float = 0.0, tutor: int = 0) -> Topic:
    t = get_or_create_topic(db, user_id, subject_id, name)
    t.questions_answered += answered
    t.questions_correct += int(round(correct)) if answered else 0
    t.tutor_messages += tutor
    t.last_studied_at = utcnow()
    if not t.status_manual:
        t.status = compute_status(t)
    return t
