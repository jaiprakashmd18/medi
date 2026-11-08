"""Document processing pipeline.

UPLOAD -> VALIDATION -> STORAGE  (done synchronously in the upload request)
-> EXTRACTION -> OCR -> IMAGE ANALYSIS -> CHUNKING -> EMBEDDINGS -> INDEXING -> READY
(run in a background worker thread; every stage updates Document.status).

The pipeline is idempotent: re-running it (retry) clears previously derived
rows, files and vectors for the document first.
"""
from __future__ import annotations

import logging
import time
import traceback
from pathlib import Path

from sqlalchemy import delete

from app.db.session import session_scope
from app.models import Chunk, Document, DocumentImage, DocumentPage, utcnow
from app.rag.vectorstore import EmbeddingUnavailable, get_vector_store
from app.services.storage import get_storage
from app.services.subjects import suggest_subject

from .chunking import chunk_page
from .extractors import EXTRACTORS
from .injection import looks_like_injection
from .preview import convert_to_pdf

log = logging.getLogger(__name__)

TERMINAL = {"ready", "partial", "failed"}
ACTIVE = {"uploaded", "validating", "stored", "extracting", "ocr", "analysing_images", "chunking",
          "embedding", "indexing"}


def _set(document_id: str, status: str | None = None, progress: int | None = None, message: str | None = None,
         **fields) -> None:
    with session_scope() as db:
        doc = db.get(Document, document_id)
        if doc is None:
            return
        if status:
            doc.status = status
        if progress is not None:
            doc.progress = max(0, min(100, progress))
        if message is not None:
            doc.stage_message = message[:300]
        for k, v in fields.items():
            setattr(doc, k, v)


def clear_derived(document_id: str) -> None:
    storage = get_storage()
    try:
        get_vector_store().delete_document(document_id)
    except Exception as exc:  # pragma: no cover
        log.warning("vector delete failed for %s: %s", document_id, exc)
    with session_scope() as db:
        db.execute(delete(Chunk).where(Chunk.document_id == document_id))
        db.execute(delete(DocumentImage).where(DocumentImage.document_id == document_id))
        db.execute(delete(DocumentPage).where(DocumentPage.document_id == document_id))
    storage.delete_tree(storage.derived_key(document_id))


def process_document(document_id: str) -> None:
    started = time.monotonic()
    storage = get_storage()
    with session_scope() as db:
        doc = db.get(Document, document_id)
        if doc is None:
            return
        file_type, stored_path, user_id = doc.file_type, doc.stored_path, doc.user_id
        doc.processing_attempts += 1
        doc.error_message = None
        doc.warnings = []
    src = storage.path(stored_path)
    warnings: list[str] = []

    try:
        if not src.exists():
            raise FileNotFoundError("The original file is missing from storage.")
        clear_derived(document_id)

        # ---- EXTRACTION (+ OCR) --------------------------------------------
        _set(document_id, "extracting", 5, "Extracting text, tables and images")
        last = [0.0]

        def on_progress(n: int, total: int, ocr_used: bool) -> None:
            now = time.monotonic()
            if now - last[0] < 0.5 and n != total:
                return
            last[0] = now
            stage = "ocr" if ocr_used else "extracting"
            label = "Running OCR on scanned content" if ocr_used else "Extracting text, tables and images"
            _set(document_id, stage, 5 + int(45 * n / max(1, total)), f"{label} ({n}/{total})")

        extracted = EXTRACTORS[file_type](src, progress=on_progress)
        warnings.extend(extracted.warnings)
        pages = extracted.pages
        if not pages:
            raise ValueError("No pages or slides could be read from this file.")

        # ---- IMAGE ANALYSIS (save originals, OCR labels done in extractor) --
        _set(document_id, "analysing_images", 55, "Saving extracted diagrams and images")
        image_ids: dict[tuple[int, int], int] = {}
        with session_scope() as db:
            for pg in pages:
                db.add(DocumentPage(
                    document_id=document_id, page_number=pg.number, kind=pg.kind, title=(pg.title or None) and pg.title[:500],
                    text=pg.text, notes=pg.notes, tables=[{"index": t["index"], "markdown": t["markdown"]} for t in pg.tables],
                    headings=pg.headings, is_scanned=pg.is_scanned, ocr_used=pg.ocr_used,
                    ocr_confidence=pg.ocr_confidence, status=pg.status, error=pg.error, warnings=pg.warnings,
                    width=pg.width, height=pg.height))
                for img in pg.images:
                    key = storage.derived_key(document_id, "images", f"p{pg.number:04d}_{img.index:02d}.{img.ext}")
                    storage.write_bytes(key, img.data)
                    row = DocumentImage(document_id=document_id, page_number=pg.number, index_on_page=img.index,
                                        path=key, mime_type="image/jpeg" if img.ext == "jpg" else "image/png",
                                        width=img.width, height=img.height, ocr_text=img.ocr_text, origin="original")
                    db.add(row)
                    db.flush()
                    image_ids[(pg.number, img.index)] = row.id
            image_count = len(image_ids)

        # ---- PREVIEW (PPTX/DOCX -> PDF for faithful slide rendering) -------
        preview_key = None
        if file_type in ("pptx", "docx"):
            _set(document_id, None, 60, "Preparing visual preview")
            key = storage.derived_key(document_id, "preview.pdf")
            ok, msg = convert_to_pdf(src, storage.path(key))
            if ok:
                preview_key = key
            else:
                warnings.append(msg)

        # ---- CHUNKING -------------------------------------------------------
        _set(document_id, "chunking", 65, "Splitting content into study passages")
        chunk_rows: list[Chunk] = []
        for pg in pages:
            image_texts = [(img.index, img.ocr_text) for img in pg.images if img.ocr_text]
            drafts = chunk_page(pg.number, pg.title, pg.text, pg.notes, pg.tables, image_texts)
            for i, d in enumerate(drafts):
                chunk_rows.append(Chunk(
                    document_id=document_id, user_id=user_id, page_number=d.page_number, chunk_index=i,
                    kind=d.kind, section=(d.section or None) and d.section[:500], text=d.text,
                    image_id=image_ids.get((pg.number, d.image_index)) if d.image_index is not None else None,
                    suspicious=looks_like_injection(d.text)))
        if any(c.suspicious for c in chunk_rows):
            n = sum(c.suspicious for c in chunk_rows)
            warnings.append(f"{n} passage(s) contain text resembling AI instructions; they are treated strictly as "
                            "document content, never as commands.")
        with session_scope() as db:
            db.add_all(chunk_rows)
        chunk_ids = [c.id for c in chunk_rows]

        # ---- EMBEDDINGS + INDEXING -----------------------------------------
        if chunk_rows:
            _set(document_id, "embedding", 72, f"Creating local embeddings for {len(chunk_rows)} passages")
            store = get_vector_store()
            texts = [((c.section + "\n") if c.section else "") + c.text for c in chunk_rows]
            metas = [{"user_id": user_id, "document_id": document_id, "page_number": c.page_number,
                      "kind": c.kind} for c in chunk_rows]
            _set(document_id, "indexing", 85, "Indexing passages in the knowledge base")
            store.upsert(chunk_ids, texts, metas)
            with session_scope() as db:
                db.query(Chunk).filter(Chunk.document_id == document_id).update({Chunk.indexed: True})
        else:
            warnings.append("No text could be extracted, so this document is not searchable by the AI tutor.")

        # ---- FINALISE -------------------------------------------------------
        failed_pages = [p.number for p in pages if p.status == "failed"]
        partial_pages = [p.number for p in pages if p.status == "partial"]
        if failed_pages:
            warnings.append(f"{len(failed_pages)} page(s) failed to extract: {failed_pages[:20]}")
        if partial_pages:
            warnings.append(f"{len(partial_pages)} page(s) only partially extracted: {partial_pages[:20]}")
        if len(failed_pages) == len(pages):
            raise ValueError("Every page failed to extract.")
        final = "partial" if (failed_pages or partial_pages or not chunk_rows) else "ready"

        with session_scope() as db:
            doc = db.get(Document, document_id)
            if doc is None:  # deleted while processing
                clear_derived(document_id)
                return
            doc.page_count = len(pages)
            doc.chunk_count = len(chunk_rows)
            doc.image_count = image_count
            doc.outline = extracted.outline[:300]
            doc.preview_pdf_path = preview_key
            doc.warnings = warnings
            if doc.subject_id is None:
                sample = "\n".join(p.text for p in pages)[:200000]
                subj, _ = suggest_subject(db, sample)
                if subj:
                    doc.subject_id = subj.id
                    doc.subject_suggested = True
            doc.status = final
            doc.progress = 100
            doc.stage_message = (f"Ready - {len(pages)} {'slides' if file_type == 'pptx' else 'pages'}, "
                                 f"{len(chunk_rows)} passages, {image_count} images "
                                 f"({time.monotonic() - started:.1f}s)")
            doc.processed_at = utcnow()
    except EmbeddingUnavailable as exc:
        log.error("Embedding failed for %s: %s", document_id, exc)
        _set(document_id, "failed", None, "Indexing failed", error_message=str(exc), warnings=warnings)
    except Exception as exc:
        log.error("Processing failed for %s: %s\n%s", document_id, exc, traceback.format_exc())
        _set(document_id, "failed", None, "Processing failed", error_message=_friendly(exc), warnings=warnings)


def _friendly(exc: Exception) -> str:
    msg = str(exc) or exc.__class__.__name__
    name = exc.__class__.__name__
    if "password" in msg.lower():
        return msg
    if name in ("FileDataError", "EmptyFileError"):
        return f"The file appears to be corrupted or is not a valid document ({msg})."
    if name == "PackageNotFoundError":
        return "The Office file appears to be corrupted and could not be opened."
    return msg


def original_path(doc: Document) -> Path:
    return get_storage().path(doc.stored_path)
