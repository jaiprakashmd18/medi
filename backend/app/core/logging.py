"""Logging setup with secret redaction so API keys never reach log output."""
from __future__ import annotations

import logging
import re

from .config import get_settings

_SECRET_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"(?i)(api[_-]?key|authorization|x-api-key)(\"?\s*[:=]\s*\"?)([^\s\"',]+)"),
    re.compile(r"(access_token=)[^&\s\"]+"),
]


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # pragma: no cover - malformed record
            return True
        redacted = redact(msg)
        if redacted != msg:
            record.msg = redacted
            record.args = ()
        return True


def redact(text: str) -> str:
    text = _SECRET_PATTERNS[0].sub("sk-ant-***REDACTED***", text)
    text = _SECRET_PATTERNS[1].sub(lambda m: f"{m.group(1)}{m.group(2)}***REDACTED***", text)
    text = _SECRET_PATTERNS[2].sub(r"\1***REDACTED***", text)
    key = get_settings().anthropic_api_key
    if key and len(key) > 8:
        text = text.replace(key, "***REDACTED***")
    return text


def setup_logging() -> None:
    settings = get_settings()
    root = logging.getLogger()
    if getattr(root, "_medigenius_configured", False):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
    handler.addFilter(RedactingFilter())
    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())
    for noisy in ("httpx", "httpx2", "chromadb", "onnxruntime", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    # uvicorn's access log includes query strings (?access_token=...): redact there too
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        logging.getLogger(name).addFilter(RedactingFilter())
    root._medigenius_configured = True  # type: ignore[attr-defined]
