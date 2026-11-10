"""Study-session tracking. Consecutive activity of the same kind on the same
document within 30 minutes is merged into one session."""
from __future__ import annotations

from datetime import timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import StudySession, utcnow

MERGE_WINDOW = timedelta(minutes=30)


def _aware(dt):
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def record_activity(db: Session, user_id: str, kind: str, *, document_id: str | None = None,
                    conversation_id: str | None = None, quiz_id: str | None = None, title: str = "") -> StudySession:
    now = utcnow()
    last = db.scalar(select(StudySession).where(StudySession.user_id == user_id)
                     .order_by(StudySession.last_activity_at.desc()).limit(1))
    if (last and last.kind == kind and last.document_id == document_id
            and (conversation_id is None or last.conversation_id in (None, conversation_id))
            and now - _aware(last.last_activity_at) < MERGE_WINDOW):
        last.last_activity_at = now
        last.activity_count += 1
        if conversation_id:
            last.conversation_id = conversation_id
        return last
    sess = StudySession(user_id=user_id, kind=kind, document_id=document_id, conversation_id=conversation_id,
                        quiz_id=quiz_id, title=title[:300], started_at=now, last_activity_at=now)
    db.add(sess)
    return sess
