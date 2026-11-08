"""Chunking that never crosses a page/slide boundary, so every chunk can be
cited to exactly one page or slide."""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.config import get_settings


@dataclass
class ChunkDraft:
    page_number: int
    kind: str
    section: str | None
    text: str
    image_index: int | None = None


def _split_text(text: str, size: int, overlap: int) -> list[str]:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) <= size:
        return [text] if text else []
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    pieces: list[str] = []
    for p in paras:
        if len(p) <= size:
            pieces.append(p)
        else:  # split long paragraph by sentences
            sents = re.split(r"(?<=[.!?;:])\s+|\n", p)
            cur = ""
            for s in sents:
                if len(cur) + len(s) + 1 > size and cur:
                    pieces.append(cur.strip())
                    cur = ""
                while len(s) > size:
                    pieces.append(s[:size])
                    s = s[size - overlap:]
                cur += " " + s
            if cur.strip():
                pieces.append(cur.strip())
    chunks: list[str] = []
    cur = ""
    for piece in pieces:
        if cur and len(cur) + len(piece) + 2 > size:
            chunks.append(cur.strip())
            tail = cur[-overlap:]
            cut = tail.find(" ")
            cur = (tail[cut + 1:] if cut >= 0 else tail) + "\n\n" + piece
        else:
            cur = (cur + "\n\n" + piece) if cur else piece
    if cur.strip():
        chunks.append(cur.strip())
    return chunks


def chunk_page(page_number: int, title: str | None, text: str, notes: str, tables: list[dict],
               image_texts: list[tuple[int, str]]) -> list[ChunkDraft]:
    s = get_settings()
    drafts: list[ChunkDraft] = []
    for piece in _split_text(text, s.chunk_size_chars, s.chunk_overlap_chars):
        if len(piece) >= 15:
            drafts.append(ChunkDraft(page_number, "text", title, piece))
    for t in tables:
        md = t.get("markdown", "")
        for piece in _split_text(md, s.chunk_size_chars * 2, 0):
            drafts.append(ChunkDraft(page_number, "table", title, piece))
    if notes.strip():
        for piece in _split_text(notes, s.chunk_size_chars, s.chunk_overlap_chars):
            drafts.append(ChunkDraft(page_number, "notes", title, piece))
    for idx, txt in image_texts:
        if txt.strip():
            drafts.append(ChunkDraft(page_number, "image_text", title, txt.strip()[: s.chunk_size_chars], idx))
    return drafts
