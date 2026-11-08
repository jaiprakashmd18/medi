"""Format-specific extraction of text, tables, images, notes and structure.

Every extractor returns an :class:`ExtractedDocument` whose pages keep their
original 1-based page/slide/section number. Failures are recorded per page
(status + error) instead of discarding the page.
"""
from __future__ import annotations

import hashlib
import io
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median
from typing import Any

from PIL import Image

from app.core.config import get_settings

from .ocr import ocr_available, ocr_image, tesseract_status

log = logging.getLogger(__name__)


@dataclass
class ExtractedImage:
    data: bytes
    ext: str
    width: int
    height: int
    index: int
    ocr_text: str = ""


@dataclass
class ExtractedPage:
    number: int
    kind: str = "page"
    title: str | None = None
    text: str = ""
    notes: str = ""
    tables: list[dict[str, Any]] = field(default_factory=list)
    headings: list[str] = field(default_factory=list)
    images: list[ExtractedImage] = field(default_factory=list)
    is_scanned: bool = False
    ocr_used: bool = False
    ocr_confidence: float | None = None
    status: str = "ok"
    error: str | None = None
    warnings: list[str] = field(default_factory=list)
    width: float | None = None
    height: float | None = None


@dataclass
class ExtractedDocument:
    pages: list[ExtractedPage]
    outline: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def rows_to_markdown(rows: list[list[Any]]) -> str:
    clean = [[re.sub(r"\s+", " ", str(c if c is not None else "")).strip() for c in r] for r in rows if r]
    clean = [r for r in clean if any(r)]
    if not clean:
        return ""
    width = max(len(r) for r in clean)
    clean = [r + [""] * (width - len(r)) for r in clean]
    head, *body = clean
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * width]
    lines += ["| " + " | ".join(r) + " |" for r in body]
    return "\n".join(lines)


def _image_info(data: bytes) -> tuple[int, int, str] | None:
    try:
        with Image.open(io.BytesIO(data)) as im:
            return im.width, im.height, (im.format or "png").lower()
    except Exception:
        return None


def _normalise_image(data: bytes) -> tuple[bytes, str, int, int] | None:
    """Convert to a browser-friendly PNG/JPEG. Returns None if undecodable."""
    try:
        with Image.open(io.BytesIO(data)) as im:
            im.load()
            fmt = (im.format or "").lower()
            w, h = im.width, im.height
            if fmt in ("png", "jpeg", "jpg") and im.mode in ("RGB", "RGBA", "L", "P"):
                return data, ("jpg" if fmt in ("jpeg", "jpg") else "png"), w, h
            out = io.BytesIO()
            conv = im.convert("RGBA" if "A" in im.mode else "RGB")
            conv.save(out, format="PNG")
            return out.getvalue(), "png", w, h
    except Exception:
        return None


def _ocr_extracted_image(img: ExtractedImage) -> None:
    """OCR an embedded diagram for its labels (best effort)."""
    settings = get_settings()
    if not ocr_available() or min(img.width, img.height) < max(150, settings.min_image_px):
        return
    try:
        with Image.open(io.BytesIO(img.data)) as im:
            text, conf = ocr_image(im)
        if text and (conf is None or conf > 45) and len(re.findall(r"[A-Za-z]{3,}", text)) >= 2:
            img.ocr_text = text
    except Exception as exc:  # pragma: no cover - OCR quirks
        log.debug("image OCR failed: %s", exc)


def _collect_images(page: ExtractedPage, raw: list[tuple[bytes, str | None]], seen: set[str]) -> None:
    settings = get_settings()
    skipped_small = 0
    dupes = 0
    undecodable = 0
    for data, _ in raw:
        digest = hashlib.sha1(data).hexdigest()
        if digest in seen:
            dupes += 1
            continue
        norm = _normalise_image(data)
        if norm is None:
            undecodable += 1
            continue
        data2, ext, w, h = norm
        if min(w, h) < settings.min_image_px:
            skipped_small += 1
            continue
        seen.add(digest)
        img = ExtractedImage(data=data2, ext=ext, width=w, height=h, index=len(page.images))
        _ocr_extracted_image(img)
        page.images.append(img)
    if skipped_small:
        page.warnings.append(f"{skipped_small} small decorative image(s) (<{settings.min_image_px}px) not extracted")
    if dupes:
        page.warnings.append(f"{dupes} repeated image(s) already extracted from an earlier page")
    if undecodable:
        page.warnings.append(f"{undecodable} embedded image(s) could not be decoded")


# --------------------------------------------------------------------------- PDF
def extract_pdf(path: Path, progress=None) -> ExtractedDocument:
    import pymupdf

    settings = get_settings()
    doc = pymupdf.open(str(path))
    if doc.needs_pass:
        raise ValueError("This PDF is password-protected. Remove the password and upload again.")
    result = ExtractedDocument(pages=[])
    try:
        toc = doc.get_toc(simple=True)
    except Exception:
        toc = []
    result.outline = [{"level": lvl, "title": title.strip(), "page": max(1, pg)} for lvl, title, pg in toc if title.strip()]
    toc_by_page: dict[int, str] = {}
    for item in result.outline:
        toc_by_page.setdefault(item["page"], item["title"])

    ocr_ok, ocr_msg = tesseract_status()
    seen: set[str] = set()
    for i in range(doc.page_count):
        number = i + 1
        page = ExtractedPage(number=number, kind="page")
        try:
            p = doc.load_page(i)
            page.width, page.height = float(p.rect.width), float(p.rect.height)
            text = p.get_text("text", sort=True) or ""
            page.headings = _pdf_headings(p)
            page.title = toc_by_page.get(number) or (page.headings[0] if page.headings else None)

            # tables
            try:
                tabs = p.find_tables()
                for t_index, t in enumerate(tabs.tables):
                    rows = t.extract()
                    md = rows_to_markdown(rows)
                    if md:
                        page.tables.append({"index": t_index, "rows": rows, "markdown": md})
            except Exception as exc:
                page.warnings.append(f"Table detection failed: {exc}")

            # images
            raw: list[tuple[bytes, str | None]] = []
            img_list = p.get_images(full=True)
            for info in img_list:
                try:
                    extracted = doc.extract_image(info[0])
                    if extracted and extracted.get("image"):
                        raw.append((extracted["image"], extracted.get("ext")))
                except Exception:
                    page.warnings.append("An embedded image could not be read")
            _collect_images(page, raw, seen)

            # scanned page detection -> OCR
            visible_chars = len(re.sub(r"\s", "", text))
            if visible_chars < settings.ocr_min_text_chars and (img_list or visible_chars == 0):
                page.is_scanned = bool(img_list)
                if ocr_ok:
                    pix = p.get_pixmap(dpi=300)
                    im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                    ocr_text, conf = ocr_image(im)
                    page.ocr_used = True
                    page.ocr_confidence = conf
                    if ocr_text:
                        text = (text + "\n" + ocr_text).strip()
                        if conf is not None and conf < 60:
                            page.warnings.append(f"Low OCR confidence ({conf:.0f}%) - verify the text")
                    elif visible_chars == 0 and not img_list:
                        page.warnings.append("Page appears to be blank")
                elif page.is_scanned:
                    page.status = "partial"
                    page.warnings.append(f"Scanned page needs OCR but OCR is unavailable: {ocr_msg}")
            page.text = text.strip()
            if progress:
                progress(number, doc.page_count, page.ocr_used)
        except Exception as exc:
            log.exception("PDF page %s failed", number)
            page.status = "failed"
            page.error = f"Could not extract page {number}: {exc}"
        result.pages.append(page)
    doc.close()
    return result


def _pdf_headings(p) -> list[str]:
    """Heuristic heading detection: short lines with font size well above body text."""
    try:
        d = p.get_text("dict")
    except Exception:
        return []
    sizes: list[float] = []
    lines: list[tuple[float, bool, str]] = []
    for block in d.get("blocks", []):
        for line in block.get("lines", []):
            spans = [s for s in line.get("spans", []) if s.get("text", "").strip()]
            if not spans:
                continue
            txt = " ".join(s["text"].strip() for s in spans).strip()
            size = max(s.get("size", 0) for s in spans)
            bold = any("bold" in s.get("font", "").lower() or (s.get("flags", 0) & 16) for s in spans)
            sizes.extend(s.get("size", 0) for s in spans)
            lines.append((size, bold, txt))
    if not sizes:
        return []
    body = median(sizes)
    out: list[str] = []
    for size, bold, txt in lines:
        if 2 < len(txt) < 120 and (size >= body * 1.25 or (bold and size >= body * 1.1)) and not txt.endswith("."):
            if txt not in out:
                out.append(txt)
    return out[:8]


# --------------------------------------------------------------------------- PPTX
def extract_pptx(path: Path, progress=None) -> ExtractedDocument:
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    prs = Presentation(str(path))
    result = ExtractedDocument(pages=[])
    seen: set[str] = set()

    def walk(shapes):
        for sh in shapes:
            if sh.shape_type == MSO_SHAPE_TYPE.GROUP:
                yield from walk(sh.shapes)
            else:
                yield sh

    for i, slide in enumerate(prs.slides):
        number = i + 1
        page = ExtractedPage(number=number, kind="slide",
                             width=float(prs.slide_width or 0) / 12700, height=float(prs.slide_height or 0) / 12700)
        try:
            texts: list[str] = []
            raw_images: list[tuple[bytes, str | None]] = []
            title_shape = slide.shapes.title
            if title_shape is not None and title_shape.has_text_frame and title_shape.text_frame.text.strip():
                page.title = title_shape.text_frame.text.strip()
            for sh in walk(slide.shapes):
                try:
                    if sh.has_text_frame and sh.text_frame.text.strip():
                        if title_shape is not None and sh.shape_id == title_shape.shape_id:
                            continue
                        paras = []
                        for para in sh.text_frame.paragraphs:
                            t = "".join(r.text for r in para.runs).strip() or para.text.strip()
                            if t:
                                paras.append(("  " * para.level) + ("• " if para.level or len(sh.text_frame.paragraphs) > 1 else "") + t)
                        texts.append("\n".join(paras))
                    if getattr(sh, "has_table", False) and sh.has_table:
                        rows = [[cell.text for cell in row.cells] for row in sh.table.rows]
                        md = rows_to_markdown(rows)
                        if md:
                            page.tables.append({"index": len(page.tables), "rows": rows, "markdown": md})
                    if sh.shape_type == MSO_SHAPE_TYPE.PICTURE or hasattr(sh, "image"):
                        try:
                            raw_images.append((sh.image.blob, sh.image.ext))
                        except Exception:
                            pass
                    if getattr(sh, "has_chart", False) and sh.has_chart:
                        page.warnings.append("Slide contains a chart; chart data is not extracted as an image")
                except Exception as exc:
                    page.warnings.append(f"A shape could not be read: {exc}")
            if page.title:
                page.headings = [page.title]
            page.text = "\n\n".join(texts).strip()
            if slide.has_notes_slide and slide.notes_slide.notes_text_frame is not None:
                page.notes = slide.notes_slide.notes_text_frame.text.strip()
            _collect_images(page, raw_images, seen)
            if not page.text and not page.title and page.images:
                page.is_scanned = True
                ocr_bits = [img.ocr_text for img in page.images if img.ocr_text]
                if ocr_bits:
                    page.ocr_used = True
                    page.text = "\n".join(ocr_bits)
                elif not ocr_available():
                    page.status = "partial"
                    page.warnings.append("Slide is image-only and OCR is unavailable")
        except Exception as exc:
            log.exception("PPTX slide %s failed", number)
            page.status = "failed"
            page.error = f"Could not extract slide {number}: {exc}"
        result.pages.append(page)
        if progress:
            progress(number, len(prs.slides), page.ocr_used)
        if page.title:
            result.outline.append({"level": 1, "title": page.title, "page": number})
    return result


# --------------------------------------------------------------------------- DOCX
def extract_docx(path: Path, progress=None) -> ExtractedDocument:
    """DOCX has no fixed pages; we split into sections at Heading 1/2 boundaries
    (max ~6000 chars each) and cite them as "section N"."""
    import docx
    from docx.oxml.ns import qn

    d = docx.Document(str(path))
    result = ExtractedDocument(pages=[])
    sections: list[ExtractedPage] = []
    current = ExtractedPage(number=1, kind="section")
    buf: list[str] = []
    seen: set[str] = set()
    image_rels = {r.rId: r for r in d.part.rels.values() if "image" in r.reltype}

    def flush():
        nonlocal current, buf
        current.text = "\n".join(buf).strip()
        if current.text or current.tables or current.images:
            sections.append(current)
        current = ExtractedPage(number=len(sections) + 1, kind="section")
        buf = []

    body = d.element.body
    for child in body.iterchildren():
        tag = child.tag.split("}")[-1]
        if tag == "p":
            from docx.text.paragraph import Paragraph

            para = Paragraph(child, d)
            style = (para.style.name if para.style is not None else "") or ""
            text = para.text.strip()
            level = None
            m = re.match(r"Heading (\d)", style)
            if m:
                level = int(m.group(1))
            elif style == "Title":
                level = 0
            if level is not None and level <= 2 and text and (buf or current.tables):
                flush()
            if level is not None and text:
                current.headings.append(text)
                current.title = current.title or text
                result.outline.append({"level": max(1, level), "title": text, "page": current.number})
                buf.append(("#" * max(1, level)) + " " + text)
            elif text:
                buf.append(("• " + text) if "List" in style else text)
            # inline images
            raw = []
            for blip in child.iter(qn("a:blip")):
                rid = blip.get(qn("r:embed"))
                if rid and rid in image_rels:
                    try:
                        raw.append((image_rels[rid].target_part.blob, None))
                    except Exception:
                        current.warnings.append("An embedded image could not be read")
            if raw:
                _collect_images(current, raw, seen)
            if sum(len(b) for b in buf) > 6000:
                flush()
        elif tag == "tbl":
            from docx.table import Table

            tbl = Table(child, d)
            try:
                rows = [[c.text for c in r.cells] for r in tbl.rows]
                md = rows_to_markdown(rows)
                if md:
                    current.tables.append({"index": len(current.tables), "rows": rows, "markdown": md})
            except Exception as exc:
                current.warnings.append(f"A table could not be read: {exc}")
    flush()
    for i, s in enumerate(sections):
        s.number = i + 1
    # outline page refs were assigned before renumbering; recompute by title
    title_to_num = {}
    for s in sections:
        for h in s.headings:
            title_to_num.setdefault(h, s.number)
    for item in result.outline:
        item["page"] = title_to_num.get(item["title"], item["page"])
    if not sections:
        sections = [ExtractedPage(number=1, kind="section", status="partial",
                                  warnings=["The document contains no readable text"])]
    result.pages = sections
    return result


# --------------------------------------------------------------------------- images
def extract_image(path: Path, progress=None) -> ExtractedDocument:
    data = path.read_bytes()
    norm = _normalise_image(data)
    if norm is None:
        raise ValueError("The image could not be decoded")
    data2, ext, w, h = norm
    page = ExtractedPage(number=1, kind="image", width=w, height=h)
    img = ExtractedImage(data=data2, ext=ext, width=w, height=h, index=0)
    page.images.append(img)
    ok, msg = tesseract_status()
    if ok:
        with Image.open(io.BytesIO(data2)) as im:
            text, conf = ocr_image(im)
        page.ocr_used = True
        page.ocr_confidence = conf
        page.text = text
        img.ocr_text = text
        if not text:
            page.warnings.append("No text was detected by OCR (diagram may be unlabelled)")
    else:
        page.status = "partial"
        page.warnings.append(f"OCR unavailable: {msg}")
    return ExtractedDocument(pages=[page])


EXTRACTORS = {"pdf": extract_pdf, "pptx": extract_pptx, "docx": extract_docx, "image": extract_image}
