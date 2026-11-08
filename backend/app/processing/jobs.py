"""Background processing queue (in-process worker threads).

Documents left in an active state by a crash/restart are re-queued on startup,
so processing always reaches a terminal state (ready / partial / failed).
"""
from __future__ import annotations

import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import session_scope
from app.models import Document

from .pipeline import ACTIVE, process_document

log = logging.getLogger(__name__)


class JobQueue:
    def __init__(self, workers: int) -> None:
        self._pool = ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix="doc-worker")
        self._inflight: dict[str, Future] = {}
        self._lock = threading.Lock()

    def submit(self, document_id: str) -> bool:
        with self._lock:
            fut = self._inflight.get(document_id)
            if fut and not fut.done():
                return False
            fut = self._pool.submit(self._run, document_id)
            self._inflight[document_id] = fut
            return True

    def _run(self, document_id: str) -> None:
        try:
            process_document(document_id)
        finally:
            with self._lock:
                self._inflight.pop(document_id, None)

    def is_running(self, document_id: str) -> bool:
        with self._lock:
            fut = self._inflight.get(document_id)
            return bool(fut and not fut.done())

    def wait_all(self, timeout: float = 120) -> None:
        import concurrent.futures as cf

        with self._lock:
            futs = list(self._inflight.values())
        cf.wait(futs, timeout=timeout)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)


_queue: JobQueue | None = None


def get_queue() -> JobQueue:
    global _queue
    if _queue is None:
        _queue = JobQueue(get_settings().processing_workers)
    return _queue


def reset_queue() -> None:
    global _queue
    if _queue is not None:
        _queue.wait_all(30)
        _queue.shutdown()
    _queue = None


def resume_interrupted() -> int:
    with session_scope() as db:
        ids = list(db.scalars(select(Document.id).where(Document.status.in_(ACTIVE))))
    for i in ids:
        log.info("Resuming interrupted processing for %s", i)
        get_queue().submit(i)
    return len(ids)
