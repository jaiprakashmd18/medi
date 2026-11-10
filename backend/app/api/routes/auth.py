from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.errors import AppError, ConflictError, UnauthorizedError
from app.core.security import create_token, hash_password, verify_password
from app.db.session import get_db
from app.models import User
from app.schemas.api import LoginIn, RegisterIn, UserOut
from app.services.users import get_user_settings

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/config")
def auth_config():
    return {"auth_mode": get_settings().auth_mode}


@router.post("/register", status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    if get_settings().auth_mode != "multi_user":
        raise AppError("Registration is only available when AUTH_MODE=multi_user.", code="auth_disabled")
    if db.scalar(select(User).where(User.email == body.email)):
        raise ConflictError("An account with this email already exists.")
    user = User(email=body.email, display_name=body.display_name, password_hash=hash_password(body.password))
    db.add(user)
    db.flush()
    get_user_settings(db, user)
    db.commit()
    return {"token": create_token(user.id), "user": UserOut.model_validate(user)}


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    if not user or not user.password_hash or not verify_password(body.password, user.password_hash):
        raise UnauthorizedError("Incorrect email or password.")
    return {"token": create_token(user.id), "user": UserOut.model_validate(user)}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
