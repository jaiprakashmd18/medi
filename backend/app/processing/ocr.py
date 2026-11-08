"""Local OCR via Tesseract (pytesseract). Availability is detected at runtime;
if Tesseract is not installed, pages that need OCR are flagged instead of
silently dropped."""
from __future__ import annotations

import logging
import shutil
from functools import lru_cache

from PIL import Image

from app.core.config import get_settings

log = logging.getLogger(__name__)


@lru_cache
def tesseract_status() -> tuple[bool, str]:
    try:
        import pytesseract
    except ImportError:
        return False, "pytesseract is not installed"
    cmd = get_settings().tesseract_cmd
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd
    elif not shutil.which("tesseract"):
        return False, ("Tesseract OCR binary not found. Install it (Windows: UB Mannheim build) "
                       "and set TESSERACT_CMD if it is not on PATH.")
    try:
        version = pytesseract.get_tesseract_version()
        return True, f"tesseract {version}"
    except Exception as exc:  # pragma: no cover - environment specific
        return False, f"Tesseract could not run: {exc}"


def ocr_available() -> bool:
    return tesseract_status()[0]


def ocr_image(img: Image.Image) -> tuple[str, float | None]:
    """Return (text, mean confidence 0-100). Raises RuntimeError if OCR unavailable."""
    ok, msg = tesseract_status()
    if not ok:
        raise RuntimeError(msg)
    import pytesseract

    lang = get_settings().tesseract_lang
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    data = pytesseract.image_to_data(img, lang=lang, output_type=pytesseract.Output.DICT)
    confs = [float(c) for c, w in zip(data["conf"], data["text"]) if str(w).strip() and float(c) >= 0]
    text = pytesseract.image_to_string(img, lang=lang)
    conf = sum(confs) / len(confs) if confs else None
    return text.strip(), conf
