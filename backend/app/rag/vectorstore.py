"""Persistent vector index (ChromaDB) with local embeddings.

Embeddings: Chroma's built-in all-MiniLM-L6-v2 ONNX model, run locally on CPU
(downloaded once to ~/.cache/chroma on first use; no document text leaves the
machine). A pluggable ``embedder`` lets tests inject a deterministic one.
"""
from __future__ import annotations

import hashlib
import logging
import math
import re
import threading
from collections.abc import Callable, Sequence
from typing import Any

from app.core.config import get_settings

log = logging.getLogger(__name__)

COLLECTION = "medigenius_chunks"
Embedder = Callable[[Sequence[str]], list[list[float]]]


class EmbeddingUnavailable(RuntimeError):
    pass


def hashing_embedder(texts: Sequence[str], dim: int = 384) -> list[list[float]]:
    """Deterministic bag-of-words hashing embedder. Used ONLY by the test-suite
    (selected with EMBEDDING_BACKEND=hashing) so tests run offline and fast."""
    out = []
    for t in texts:
        v = [0.0] * dim
        for tok in re.findall(r"[a-z0-9]+", t.lower()):
            h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
            v[h % dim] += 1.0 if (h >> 8) % 2 else -1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        out.append([x / n for x in v])
    return out


class VectorStore:
    def __init__(self, path: str, embedder: Embedder | None = None, backend_name: str = "onnx-minilm") -> None:
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        self._client = chromadb.PersistentClient(path=path, settings=ChromaSettings(anonymized_telemetry=False))
        self._col = self._client.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"},
                                                          embedding_function=None)
        self._embedder = embedder
        self.backend_name = backend_name
        self._lock = threading.Lock()

    # embeddings ---------------------------------------------------------
    def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        if self._embedder is None:
            try:
                from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

                fn = DefaultEmbeddingFunction()
                self._embedder = lambda xs: [list(map(float, e)) for e in fn(list(xs))]
            except Exception as exc:  # pragma: no cover - environment specific
                raise EmbeddingUnavailable(f"Local embedding model could not be loaded: {exc}") from exc
        try:
            return self._embedder(texts)
        except Exception as exc:
            raise EmbeddingUnavailable(
                "Local embedding model failed. On first run it must download (~80 MB) to ~/.cache/chroma; "
                f"check your internet connection. Details: {exc}") from exc

    # write --------------------------------------------------------------
    def upsert(self, ids: list[str], texts: list[str], metadatas: list[dict[str, Any]], batch: int = 64) -> None:
        for i in range(0, len(ids), batch):
            emb = self._embed(texts[i:i + batch])
            with self._lock:
                self._col.upsert(ids=ids[i:i + batch], embeddings=emb, documents=texts[i:i + batch],
                                 metadatas=metadatas[i:i + batch])

    def delete_document(self, document_id: str) -> None:
        with self._lock:
            self._col.delete(where={"document_id": document_id})

    # read ---------------------------------------------------------------
    def query(self, text: str, n: int, where: dict[str, Any]) -> list[tuple[str, float]]:
        """Return [(chunk_id, cosine_similarity)]."""
        emb = self._embed([text])
        with self._lock:
            count = self._col.count()
            if count == 0:
                return []
            res = self._col.query(query_embeddings=emb, n_results=min(n, count), where=where,
                                  include=["distances"])
        ids = res.get("ids", [[]])[0]
        dists = res.get("distances", [[]])[0]
        return [(cid, 1.0 - float(d)) for cid, d in zip(ids, dists)]

    def count(self) -> int:
        return self._col.count()

    def status(self) -> dict[str, Any]:
        return {"backend": self.backend_name, "vectors": self.count()}


_store: VectorStore | None = None
_store_lock = threading.Lock()


def get_vector_store() -> VectorStore:
    global _store
    with _store_lock:
        if _store is None:
            import os

            s = get_settings()
            backend = os.environ.get("EMBEDDING_BACKEND", "onnx-minilm")
            embedder = hashing_embedder if backend == "hashing" else None
            _store = VectorStore(str(s.vectors_dir), embedder=embedder, backend_name=backend)
        return _store


def reset_vector_store() -> None:
    global _store
    _store = None
