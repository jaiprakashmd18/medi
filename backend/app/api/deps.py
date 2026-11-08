from __future__ import annotations

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import UnauthorizedError
from app.core.security import decode_token
from app.db.session import get_db
from app.models import User
from app.services.users import get_or_create_default_user


def get_current_user(db: Session = Depends(get_db), authorization: str | None = Header(default=None)) -> User:
    settings = get_settings()
    if authorization and authorization.lower().startswith("bearer "):
        uid = decode_token(authorization.split(" ", 1)[1].strip())
        if uid:
            user = db.get(User, uid)
            if user:
                return user
        if settings.auth_mode == "multi_user":
            raise UnauthorizedError("Invalid or expired session. Please sign in again.")
    if settings.auth_mode == "single_user":
        return get_or_create_default_user(db)
    raise UnauthorizedError("Authentication required.")
