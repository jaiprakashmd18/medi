from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User, utcnow
from app.schemas.api import SettingsIn, SettingsOut
from app.services.users import get_user_settings

router = APIRouter(prefix="/settings", tags=["settings"])


def _out(user: User, st) -> SettingsOut:
    o = SettingsOut.model_validate(st)
    o.display_name = user.display_name
    return o


@router.get("", response_model=SettingsOut)
def get_settings_(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    st = get_user_settings(db, user)
    db.commit()
    return _out(user, st)


@router.put("", response_model=SettingsOut)
def update_settings(body: SettingsIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    st = get_user_settings(db, user)
    data = body.model_dump(exclude_unset=True)
    if "display_name" in data:
        user.display_name = data.pop("display_name")
    if "cloud_consent" in data:
        if data["cloud_consent"] and not st.cloud_consent:
            st.cloud_consent_at = utcnow()
        if not data["cloud_consent"]:
            st.cloud_consent_at = None
    for k, v in data.items():
        setattr(st, k, v)
    db.commit()
    return _out(user, st)
