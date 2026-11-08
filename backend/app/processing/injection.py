"""Prompt-injection hygiene for untrusted document text.

Document content is *data*. We never execute instructions found inside it.
This module (1) flags text that looks like it is trying to instruct an AI so
the UI and prompts can mark it, and (2) neutralises our own delimiter tags so
document text cannot break out of the <source> wrapper used in prompts.
"""
from __future__ import annotations

import re

_PATTERNS = [
    r"ignore (all |any |the )?(previous|prior|above) (instructions|prompts|rules)",
    r"disregard (all |the )?(previous|prior|above|system)",
    r"you are now (a|an|the)\b",
    r"new (system )?instructions?:",
    r"\bsystem prompt\b",
    r"reveal (your|the) (system )?(prompt|instructions)",
    r"act as (a|an) (?!patient|clinician|doctor)",
    r"<\s*/?\s*(system|assistant|source|instructions?)\s*>",
    r"\bjailbreak\b",
    r"do not (tell|inform) the (user|student)",
]
_RE = re.compile("|".join(_PATTERNS), re.IGNORECASE)
_TAG_RE = re.compile(r"<\s*(/?)\s*(source|sources|system|instructions?)\b[^>]*>", re.IGNORECASE)


def looks_like_injection(text: str) -> bool:
    return bool(_RE.search(text or ""))


def neutralise(text: str) -> str:
    """Escape tags that could close/open our prompt delimiters."""
    return _TAG_RE.sub(lambda m: f"[{m.group(1)}{m.group(2)}]", text or "")
