from __future__ import annotations

import platform

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai import router as ai_router
from app.api.deps import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models import User
from app.processing.ocr import tesseract_status
from app.processing.preview import soffice_path
from app.rag.vectorstore import get_vector_store
from app.services.users import get_user_settings

router = APIRouter(tags=["system"])

VERSION = "0.1.0"


@router.get("/health")
def health(db: Session = Depends(get_db)):
    s = get_settings()
    checks: dict = {}
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = {"ok": True, "detail": s.sqlalchemy_url.split(":///")[0]}
    except Exception as exc:  # pragma: no cover
        checks["database"] = {"ok": False, "detail": str(exc)}
    try:
        checks["vector_store"] = {"ok": True, **get_vector_store().status()}
    except Exception as exc:  # pragma: no cover
        checks["vector_store"] = {"ok": False, "detail": str(exc)}
    ok, msg = tesseract_status()
    checks["ocr"] = {"ok": ok, "detail": msg}
    sp = soffice_path()
    checks["office_preview"] = {"ok": bool(sp), "detail": "LibreOffice found" if sp else
                                "LibreOffice not found - PPTX/DOCX shown as extracted content"}
    checks["storage"] = {"ok": s.data_dir.exists(), "detail": "local filesystem"}
    status = "ok" if checks["database"]["ok"] and checks["vector_store"]["ok"] else "degraded"
    return {"status": status, "app": s.app_name, "version": VERSION, "environment": s.app_env,
            "python": platform.python_version(), "auth_mode": s.auth_mode, "checks": checks}


@router.get("/ai/providers")
def providers(refresh: bool = False, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    st = get_user_settings(db, user)
    out = []
    for name in ("anthropic", "ollama"):
        h = ai_router.get_provider(name).health(force=refresh)
        out.append({"name": h.name, "label": "Claude (Anthropic API)" if name == "anthropic" else "Ollama (local)",
                    "kind": h.kind, "configured": h.configured, "available": h.available, "detail": h.detail,
                    "models": h.models, "installed_models": h.installed_models})
    routes = {}
    for task in ("explain", "simple", "vision", "generate"):
        try:
            sel = ai_router.select(task, st.ai_mode, st.cloud_consent)  # type: ignore[arg-type]
            routes[task] = {"provider": sel.provider.name, "model": sel.model, "reason": sel.reason, "ok": True}
        except Exception as exc:
            routes[task] = {"ok": False, "reason": getattr(exc, "message", str(exc)), "code": getattr(exc, "code", "")}
    from app.rag import nvidia_reranker

    allowed, reason = nvidia_reranker.rerank_allowed(st.ai_mode, st.nvidia_consent)
    reranker = {**nvidia_reranker.status(), "active_for_you": allowed, "reason": reason,
                "nvidia_consent": st.nvidia_consent}
    return {"mode": st.ai_mode, "cloud_consent": st.cloud_consent, "providers": out, "routes": routes,
            "reranker": reranker,
            "billing_note": "Claude API usage is billed separately by Anthropic; a Claude Pro/Max subscription does "
                            "not include API credits."}
