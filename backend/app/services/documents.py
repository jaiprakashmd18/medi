"""Document library operations: upload, query, rename, delete."""
from __future__ import annotations

import hashlib
import logging

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import NotFoundError, ValidationFailed
from app.models import Chunk, Document, DocumentImage, DocumentPage, Subject, Topic, User
from app.processing.jobs import get_queue
from app.processing.pipeline import clear_derived
from app.processing.validation import detect, safe_filename
from app.rag.retriever import page_kind_for
from app.services.storage import get_storage

log = logging.getLogger(__name__)


def get_owned(db: Session, user: User, document_id: str) -> Document:
    doc = db.get(Document, document_id)
    if doc is None or doc.user_id != user.id:
        raise NotFoundError("Document not found.")
    return doc


def create_from_upload(db: Session, user: User, filename: str, data: bytes, subject_id: int | None) -> Document:
    settings = get_settings()
    name = safe_filename(filename)
    file_type, mime, ext = detect(name, data, settings.max_upload_mb * 1024 * 1024)
    if subject_id is not None:
        subj = db.get(Subject, subject_id)
        if subj is None or (subj.user_id not in (None, user.id)):
            raise ValidationFailed("Unknown subject.")
    sha = hashlib.sha256(data).hexdigest()
    title = name.rsplit(".", 1)[0].replace("_", " ").strip() or name
    doc = Document(user_id=user.id, title=title[:300], original_filename=name, file_type=file_type, mime_type=mime,
                   size_bytes=len(data), sha256=sha, status="validating", progress=1,
                   stage_message="Validated", subject_id=subject_id, stored_path="")
    db.add(doc)
    db.flush()
    duplicate = db.scalar(select(Document).where(Document.user_id == user.id, Document.sha256 == sha,
                                                 Document.id != doc.id))
    key = get_storage().original_key(user.id, doc.id, ext)
    get_storage().write_bytes(key, data)
    doc.stored_path = key
    doc.status = "stored"
    doc.progress = 3
    doc.stage_message = "Stored securely; queued for processing"
    if duplicate:
        doc.warnings = [f"This file is identical to '{duplicate.title}', which is already in your library."]
    db.commit()
    get_queue().submit(doc.id)
    return doc


def reprocess(db: Session, user: User, document_id: str) -> Document:
    doc = get_owned(db, user, document_id)
    if get_queue().is_running(doc.id):
        return doc
    doc.status = "stored"
    doc.progress = 3
    doc.stage_message = "Queued for reprocessing"
    doc.error_message = None
    db.commit()
    get_queue().submit(doc.id)
    return doc


def delete_document(db: Session, user: User, document_id: str) -> None:
    doc = get_owned(db, user, document_id)
    storage = get_storage()
    clear_derived(doc.id)  # vectors, chunk/page/image rows, derived files
    db.delete(doc)
    db.commit()
    storage.delete_tree(storage.upload_dir_key(user.id, document_id))


def list_documents(db: Session, user: User, q: str | None, subject_id: int | None, status: str | None,
                   file_type: str | None, sort: str) -> list[Document]:
    stmt = select(Document).where(Document.user_id == user.id)
    if q:
        like = f"%{q.lower()}%"
        sub = select(DocumentPage.document_id).where(func.lower(DocumentPage.text).like(like))
        stmt = stmt.where(or_(func.lower(Document.title).like(like), func.lower(Document.original_filename).like(like),
                              Document.id.in_(sub)))
    if subject_id is not None:
        stmt = stmt.where(Document.subject_id == subject_id)
    if status:
        stmt = stmt.where(Document.status == status)
    if file_type:
        stmt = stmt.where(Document.file_type == file_type)
    order = {"recent": Document.created_at.desc(), "title": Document.title.asc(),
             "opened": Document.last_opened_at.desc().nullslast()}.get(sort, Document.created_at.desc())
    return list(db.scalars(stmt.order_by(order)))


def serialize(doc: Document, detail: bool = False) -> dict:
    d = {c: getattr(doc, c) for c in (
        "id", "title", "original_filename", "file_type", "mime_type", "size_bytes", "status", "progress",
        "stage_message", "error_message", "warnings", "page_count", "chunk_count", "image_count", "subject_id",
        "subject_suggested", "topic_id", "created_at", "updated_at", "processed_at", "last_opened_at",
        "last_page_viewed")}
    d["warnings"] = d["warnings"] or []
    d["has_preview"] = bool(doc.file_type == "pdf" or doc.preview_pdf_path)
    if detail:
        d["outline"] = doc.outline or []
        d["page_kind"] = page_kind_for(doc.file_type)
    return d


def page_summaries(db: Session, doc: Document) -> list[dict]:
    img_counts = dict(db.execute(select(DocumentImage.page_number, func.count()).where(
        DocumentImage.document_id == doc.id).group_by(DocumentImage.page_number)).all())
    out = []
    for p in db.scalars(select(DocumentPage).where(DocumentPage.document_id == doc.id)
                        .order_by(DocumentPage.page_number)):
        out.append({"page_number": p.page_number, "kind": p.kind, "title": p.title, "status": p.status,
                    "is_scanned": p.is_scanned, "ocr_used": p.ocr_used, "image_count": img_counts.get(p.page_number, 0),
                    "table_count": len(p.tables or []), "char_count": len(p.text or ""), "has_notes": bool(p.notes)})
    return out


def counts_by_subject(db: Session, user_id: str) -> dict[int, int]:
    return dict(db.execute(select(Document.subject_id, func.count()).where(Document.user_id == user_id)
                           .group_by(Document.subject_id)).all())


def topic_counts(db: Session, user_id: str) -> dict[int, int]:
    return dict(db.execute(select(Topic.subject_id, func.count()).where(Topic.user_id == user_id)
                           .group_by(Topic.subject_id)).all())


def chunk_count(db: Session, user_id: str) -> int:
    return db.scalar(select(func.count()).select_from(Chunk).where(Chunk.user_id == user_id)) or 0
