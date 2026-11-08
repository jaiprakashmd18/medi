from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.errors import AppError, NotFoundError, PayloadTooLarge
from app.db.session import get_db
from app.models import DocumentImage, DocumentPage, User, utcnow
from app.processing.preview import render_pdf_page
from app.rag.retriever import retrieve
from app.schemas.api import DocumentDetail, DocumentOut, DocumentPatch, ImageOut, PageDetail, PageSummary, ViewedIn
from app.services import documents as svc
from app.services.activity import record_activity
from app.services.storage import get_storage

router = APIRouter(prefix="/documents", tags=["documents"])


def _image_out(img: DocumentImage) -> ImageOut:
    o = ImageOut.model_validate(img)
    o.url = f"/api/documents/{img.document_id}/images/{img.id}/file"
    return o


@router.post("/upload", status_code=201)
async def upload(files: list[UploadFile] = File(...), subject_id: int | None = Form(default=None),
                 db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    s = get_settings()
    if len(files) > s.max_files_per_upload:
        raise AppError(f"At most {s.max_files_per_upload} files per upload.", code="too_many_files")
    limit = s.max_upload_mb * 1024 * 1024
    created, errors = [], []
    for f in files:
        data = await f.read(limit + 1)
        try:
            if len(data) > limit:
                raise PayloadTooLarge(f"'{f.filename}' exceeds the {s.max_upload_mb} MB limit.")
            doc = svc.create_from_upload(db, user, f.filename or "document", data, subject_id)
            created.append(DocumentOut.model_validate(svc.serialize(doc)))
        except AppError as exc:
            db.rollback()
            errors.append({"filename": f.filename, "code": exc.code, "message": exc.message,
                           "status": exc.status_code})
    if not created and errors:
        raise AppError(errors[0]["message"], code=errors[0]["code"], status_code=errors[0]["status"],
                       details={"errors": errors})
    return {"documents": created, "errors": errors}


@router.get("", response_model=list[DocumentOut])
def list_documents(q: str | None = None, subject_id: int | None = None, status: str | None = None,
                   file_type: str | None = None, sort: str = "recent",
                   db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [svc.serialize(d) for d in svc.list_documents(db, user, q, subject_id, status, file_type, sort)]


@router.get("/{document_id}", response_model=DocumentDetail)
def get_document(document_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return svc.serialize(svc.get_owned(db, user, document_id), detail=True)


@router.get("/{document_id}/status")
def status(document_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    d = svc.get_owned(db, user, document_id)
    return {"id": d.id, "status": d.status, "progress": d.progress, "stage_message": d.stage_message,
            "error_message": d.error_message, "warnings": d.warnings or [], "page_count": d.page_count}


@router.patch("/{document_id}", response_model=DocumentOut)
def patch(document_id: str, body: DocumentPatch, db: Session = Depends(get_db),
          user: User = Depends(get_current_user)):
    d = svc.get_owned(db, user, document_id)
    if body.title is not None:
        d.title = body.title.strip()
    if body.clear_subject:
        d.subject_id = None
        d.subject_suggested = False
    elif body.subject_id is not None:
        d.subject_id = body.subject_id
        d.subject_suggested = False
    if body.topic_id is not None:
        d.topic_id = body.topic_id
    db.commit()
    return svc.serialize(d)


@router.delete("/{document_id}", status_code=204)
def delete(document_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    svc.delete_document(db, user, document_id)


@router.post("/{document_id}/reprocess", response_model=DocumentOut)
def reprocess(document_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return svc.serialize(svc.reprocess(db, user, document_id))


@router.post("/{document_id}/viewed")
def viewed(document_id: str, body: ViewedIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    d = svc.get_owned(db, user, document_id)
    d.last_opened_at = utcnow()
    d.last_page_viewed = min(body.page_number, max(1, d.page_count))
    record_activity(db, user.id, "reading", document_id=d.id, title=d.title)
    db.commit()
    return {"ok": True}


@router.get("/{document_id}/pages", response_model=list[PageSummary])
def pages(document_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return svc.page_summaries(db, svc.get_owned(db, user, document_id))


@router.get("/{document_id}/pages/{page_number}", response_model=PageDetail)
def page(document_id: str, page_number: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    d = svc.get_owned(db, user, document_id)
    p = db.scalar(select(DocumentPage).where(DocumentPage.document_id == d.id, DocumentPage.page_number == page_number))
    if p is None:
        raise NotFoundError("Page not found.")
    out = PageDetail.model_validate(p)
    out.images = [_image_out(i) for i in db.scalars(select(DocumentImage).where(
        DocumentImage.document_id == d.id, DocumentImage.page_number == page_number).order_by(DocumentImage.index_on_page))]
    out.renderable = d.file_type == "pdf" or bool(d.preview_pdf_path)
    return out


@router.get("/{document_id}/pages/{page_number}/image")
def page_image(document_id: str, page_number: int, scale: float = Query(1.5, ge=0.5, le=4.0),
               db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    d = svc.get_owned(db, user, document_id)
    storage = get_storage()
    if d.file_type == "pdf":
        pdf = storage.path(d.stored_path)
    elif d.preview_pdf_path:
        pdf = storage.path(d.preview_pdf_path)
    elif d.file_type == "image":
        return FileResponse(storage.path(d.stored_path), media_type=d.mime_type)
    else:
        raise NotFoundError("No rendered preview is available for this document (LibreOffice not installed).",
                            code="no_preview")
    try:
        path = render_pdf_page(pdf, page_number, scale, storage.path(storage.derived_key(d.id, "renders")))
    except IndexError:
        raise NotFoundError("Page not found.")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


@router.get("/{document_id}/file")
def original(document_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    d = svc.get_owned(db, user, document_id)
    return FileResponse(get_storage().path(d.stored_path), media_type=d.mime_type, filename=d.original_filename,
                        content_disposition_type="inline")


@router.get("/{document_id}/images", response_model=list[ImageOut])
def images(document_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    d = svc.get_owned(db, user, document_id)
    return [_image_out(i) for i in db.scalars(select(DocumentImage).where(DocumentImage.document_id == d.id)
                                             .order_by(DocumentImage.page_number, DocumentImage.index_on_page))]


@router.get("/{document_id}/images/{image_id}/file")
def image_file(document_id: str, image_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    d = svc.get_owned(db, user, document_id)
    img = db.get(DocumentImage, image_id)
    if img is None or img.document_id != d.id:
        raise NotFoundError("Image not found.")
    return FileResponse(get_storage().path(img.path), media_type=img.mime_type,
                        headers={"Cache-Control": "private, max-age=86400"})


search_router = APIRouter(tags=["search"])


@search_router.get("/search")
def search(q: str = Query(min_length=2, max_length=500), document_ids: list[str] = Query(default=[]),
           subject_id: int | None = None, limit: int = Query(10, ge=1, le=30),
           db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    res = retrieve(db, user.id, q, document_ids=document_ids or None, subject_id=subject_id, top_k=limit)
    return {"query": q, "note": res.note, "sufficient": res.sufficient,
            "results": [{"chunk_id": c.chunk_id, "document_id": c.document_id, "document_title": c.document_title,
                         "page_number": c.page_number, "page_kind": c.page_kind, "section": c.section, "kind": c.kind,
                         "text": c.text, "score": c.score} for c in res.chunks]}
