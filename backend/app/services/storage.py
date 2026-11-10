"""Storage abstraction. Local filesystem today; the interface is small so a
cloud object store (S3, Azure Blob...) can be added later without touching
callers. All paths stored in the database are *relative keys*.

Layout under DATA_DIR:
  uploads/<user_id>/<document_id>/original.<ext>   original files (never modified)
  derived/<document_id>/images/...                 extracted images
  derived/<document_id>/renders/...                cached page renders
  derived/<document_id>/preview.pdf                PPTX/DOCX preview (LibreOffice)
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from app.core.config import get_settings


class StorageError(Exception):
    pass


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root not in p.parents and p != self.root:
            raise StorageError("Path escapes storage root")
        return p

    def path(self, key: str) -> Path:
        return self._resolve(key)

    def write_bytes(self, key: str, data: bytes) -> str:
        p = self._resolve(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, p)
        return key

    def read_bytes(self, key: str) -> bytes:
        return self._resolve(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._resolve(key).exists()

    def delete(self, key: str) -> None:
        p = self._resolve(key)
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        elif p.exists():
            p.unlink()

    def delete_tree(self, key: str) -> None:
        self.delete(key)

    # helpers for well-known keys
    @staticmethod
    def original_key(user_id: str, document_id: str, ext: str) -> str:
        return f"uploads/{user_id}/{document_id}/original.{ext}"

    @staticmethod
    def upload_dir_key(user_id: str, document_id: str) -> str:
        return f"uploads/{user_id}/{document_id}"

    @staticmethod
    def derived_key(document_id: str, *parts: str) -> str:
        return "/".join(["derived", document_id, *parts])


_storage: LocalStorage | None = None


def get_storage() -> LocalStorage:
    global _storage
    root = get_settings().data_dir
    if _storage is None or _storage.root != root.resolve():
        _storage = LocalStorage(root)
    return _storage
