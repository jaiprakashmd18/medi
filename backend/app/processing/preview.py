"""Page rendering for the document viewer.

PDFs are rendered directly with PyMuPDF. PPTX/DOCX are converted once to a
preview PDF with LibreOffice (if installed) so slides can be shown as they
look; without LibreOffice the viewer falls back to the structured extracted
content (text, tables, images, notes) and says so.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings

log = logging.getLogger(__name__)

WINDOWS_SOFFICE = [
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
]


@lru_cache
def soffice_path() -> str | None:
    s = get_settings()
    if s.soffice_path and Path(s.soffice_path).exists():
        return s.soffice_path
    for name in ("soffice", "libreoffice"):
        p = shutil.which(name)
        if p:
            return p
    for p in WINDOWS_SOFFICE:
        if Path(p).exists():
            return p
    return None


def convert_to_pdf(src: Path, dest: Path, timeout: int = 180) -> tuple[bool, str]:
    exe = soffice_path()
    if not exe:
        return False, "LibreOffice is not installed; showing extracted slide content instead of rendered slides."
    with tempfile.TemporaryDirectory() as tmp:
        profile = Path(tmp) / "profile"
        cmd = [exe, f"-env:UserInstallation=file:///{profile.as_posix().lstrip('/')}", "--headless",
               "--convert-to", "pdf", "--outdir", tmp, str(src)]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return False, "LibreOffice preview conversion timed out."
        except OSError as exc:
            return False, f"LibreOffice could not start: {exc}"
        out = Path(tmp) / (src.stem + ".pdf")
        if proc.returncode != 0 or not out.exists():
            return False, f"LibreOffice conversion failed: {proc.stderr.decode(errors='ignore')[:300]}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(out), dest)
    return True, "ok"


def render_pdf_page(pdf_path: Path, page_number: int, scale: float, cache_dir: Path) -> Path:
    import pymupdf

    scale = max(0.5, min(4.0, round(scale * 4) / 4))
    cache = cache_dir / f"p{page_number:04d}@{scale:.2f}.png"
    if cache.exists():
        return cache
    doc = pymupdf.open(str(pdf_path))
    try:
        if page_number < 1 or page_number > doc.page_count:
            raise IndexError("page out of range")
        pix = doc.load_page(page_number - 1).get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
        cache.parent.mkdir(parents=True, exist_ok=True)
        pix.save(str(cache))
    finally:
        doc.close()
    return cache
