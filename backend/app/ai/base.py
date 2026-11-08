"""Provider-independent AI interfaces."""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Literal

TaskKind = Literal["explain", "simple", "vision", "generate"]


@dataclass
class ChatImage:
    data: bytes
    mime_type: str = "image/png"


@dataclass
class ChatMessage:
    role: Literal["user", "assistant"]
    content: str
    images: list[ChatImage] = field(default_factory=list)


@dataclass
class Completion:
    text: str
    provider: str
    model: str
    usage: dict[str, Any] = field(default_factory=dict)
    stop_reason: str | None = None


@dataclass
class ProviderHealth:
    name: str
    kind: Literal["cloud", "local"]
    configured: bool
    available: bool
    detail: str
    models: dict[str, str] = field(default_factory=dict)
    installed_models: list[str] = field(default_factory=list)


class StreamResult:
    """Iterator of text deltas; after exhaustion ``completion`` holds the final result."""

    def __init__(self, gen_factory):
        self._factory = gen_factory
        self.completion: Completion | None = None

    def __iter__(self) -> Iterator[str]:
        yield from self._factory(self)


class LLMProvider:
    name: str = "base"
    kind: Literal["cloud", "local"] = "local"

    def health(self, force: bool = False) -> ProviderHealth:  # pragma: no cover - interface
        raise NotImplementedError

    def model_for(self, task: TaskKind) -> str:  # pragma: no cover - interface
        raise NotImplementedError

    def complete(self, *, system: str, messages: list[ChatMessage], model: str, max_tokens: int = 8000,
                 json_schema: dict | None = None) -> Completion:  # pragma: no cover - interface
        raise NotImplementedError

    def stream(self, *, system: str, messages: list[ChatMessage], model: str,
               max_tokens: int = 16000) -> StreamResult:  # pragma: no cover - interface
        raise NotImplementedError
