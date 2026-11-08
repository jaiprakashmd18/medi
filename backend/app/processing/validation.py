"""Upload validation: extension + magic bytes + size, and safe filenames."""
from __future__ import annotations

import re
import unicodedata
import zipfile
import io

from app.core.errors import PayloadTooLarge, ValidationFailed

ALLOWED = {
    "pdf": ("pdf", "application/pdf"),
    "pptx": ("pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
    "docx": ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "jpg": ("image", "image/jpeg"),
    "jpeg": ("image", "image/jpeg"),
    "png": ("image", "image/png"),
}


def safe_filename(name: str) -> str:
    name = unicodedata.normalize("NFKC", name or "document")
    name = name.replace("\\", "/").split("/")[-1]
    name = re.sub(r"[\x00-\x1f<>:\"|?*]", "", name).strip(" .")
    return (name or "document")[:200]


def detect(filename: str, data: bytes, max_bytes: int) -> tuple[str, str, str]:
    """Return (file_type, mime, ext) or raise."""
    if len(data) == 0:
        raise ValidationFailed(f"'{filename}' is empty.")
    if len(data) > max_bytes:
        raise PayloadTooLarge(f"'{filename}' is {len(data) / 1e6:.1f} MB; the limit is {max_bytes / 1e6:.0f} MB.")
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED:
        raise ValidationFailed(f"'{filename}': unsupported file type. Allowed: PDF, PPTX, DOCX, JPG, JPEG, PNG.",
                               code="unsupported_type")
    file_type, mime = ALLOWED[ext]
    head = data[:8]
    ok = False
    if file_type == "pdf":
        ok = data[:1024].lstrip().startswith(b"%PDF") or b"%PDF" in data[:1024]
    elif file_type in ("pptx", "docx"):
        if head.startswith(b"PK"):
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as z:
                    names = set(z.namelist())
                ok = ("ppt/presentation.xml" in names) if file_type == "pptx" else ("word/document.xml" in names)
            except zipfile.BadZipFile:
                ok = False
    elif ext == "png":
        ok = head.startswith(b"\x89PNG\r\n\x1a\n")
    else:
        ok = head[:3] == b"\xff\xd8\xff"
    if not ok:
        raise ValidationFailed(f"'{filename}' does not look like a valid .{ext} file (content check failed).",
                               code="invalid_content")
    return file_type, mime, ("jpg" if ext == "jpeg" else ext)
