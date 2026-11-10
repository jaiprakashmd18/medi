from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import User, UserSettings

DEFAULT_EMAIL = "local@medi-genius.local"


def get_or_create_default_user(db: Session) -> User:
    user = db.scalar(select(User).where(User.is_local_default.is_(True)))
    if user is None:
        user = User(email=DEFAULT_EMAIL, display_name="Student", is_local_default=True)
        db.add(user)
        db.flush()
        get_user_settings(db, user)
        db.commit()
    return user


def get_user_settings(db: Session, user: User) -> UserSettings:
    st = db.get(UserSettings, user.id)
    if st is None:
        st = UserSettings(user_id=user.id, ai_mode=get_settings().ai_mode)
        db.add(st)
        db.flush()
    return st
