"""MEDI-GENIUS FastAPI application."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import setup_logging

log = logging.getLogger("medigenius")


def init_app_state() -> None:
    from app.db.migrate import upgrade_head
    from app.db.session import session_scope
    from app.services.subjects import seed_subjects
    from app.services.users import get_or_create_default_user

    upgrade_head()
    with session_scope() as db:
        seed_subjects(db)
        if get_settings().auth_mode == "single_user":
            get_or_create_default_user(db)


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging()
    init_app_state()
    from app.processing.jobs import resume_interrupted

    n = resume_interrupted()
    if n:
        log.info("Re-queued %d interrupted document(s)", n)
    s = get_settings()
    if s.auth_mode == "multi_user" and s.secret_key == "change-me-in-production":
        if s.app_env == "production":
            raise RuntimeError("SECRET_KEY must be set to a long random value in production multi-user mode.")
        log.warning("SECRET_KEY is the default value; set a random SECRET_KEY before sharing this server.")
    log.info("MEDI-GENIUS backend ready (data dir: %s)", get_settings().data_dir)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="MEDI-GENIUS API", version="0.1.0", lifespan=lifespan,
                  description="AI-powered medical education platform API. Educational use only - not for diagnosis "
                              "or treatment.")
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        return JSONResponse(status_code=exc.status_code, content=exc.to_dict())

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        errs = [{"field": ".".join(str(p) for p in e.get("loc", [])[1:]), "message": e.get("msg")} for e in exc.errors()]
        msg = "; ".join(f"{e['field']}: {e['message']}" for e in errs) or "Invalid request"
        return JSONResponse(status_code=422, content={"error": {"code": "validation_failed", "message": msg,
                                                                "details": {"errors": errs}}})

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        return JSONResponse(status_code=exc.status_code,
                            content={"error": {"code": "http_error", "message": str(exc.detail), "details": {}}})

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        log.exception("Unhandled error: %s", exc)
        return JSONResponse(status_code=500, content={"error": {"code": "internal_error",
                                                                "message": "An unexpected error occurred.",
                                                                "details": {}}})

    from app.api.routes import auth, documents, learning, settings as settings_routes, system

    for r in (system.router, auth.router, documents.router, documents.search_router, documents.images_router,
              settings_routes.router,
              learning.router):
        app.include_router(r, prefix="/api")
    return app


app = create_app()
