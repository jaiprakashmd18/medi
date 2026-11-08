"""Hybrid AI routing.

Modes
  auto        explain/vision/generate -> Claude (if configured AND the user consented
              to sending document excerpts to the cloud), otherwise local Ollama.
              simple -> local first, cloud second.
  local_only  Ollama only. Nothing leaves the machine.
  cloud_only  Claude only (requires consent).

The selection result records the provider that will actually run; responses
store the provider/model reported back by that provider, so the UI never
claims a local model processed a cloud request (or vice-versa).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.errors import AIUnavailableError

from .anthropic_provider import AnthropicProvider
from .base import LLMProvider, TaskKind
from .ollama_provider import OllamaProvider


@dataclass
class Selection:
    provider: LLMProvider
    model: str
    reason: str


_providers: dict[str, LLMProvider] = {}


def get_provider(name: str) -> LLMProvider:
    if name not in _providers:
        _providers[name] = AnthropicProvider() if name == "anthropic" else OllamaProvider()
    return _providers[name]


def set_provider(name: str, provider: LLMProvider) -> None:
    """Testing hook: replace a provider implementation."""
    _providers[name] = provider


def reset_providers() -> None:
    _providers.clear()


def select(task: TaskKind, mode: str, cloud_consent: bool) -> Selection:
    cloud = get_provider("anthropic")
    local = get_provider("ollama")
    ch = cloud.health()
    lh = local.health()
    cloud_ok = ch.available and cloud_consent
    local_ok = lh.available
    if task == "vision" and local_ok and isinstance(local, OllamaProvider):
        local_ok = local.vision_available()

    def use_cloud(reason: str) -> Selection:
        return Selection(cloud, cloud.model_for(task), reason)

    def use_local(reason: str) -> Selection:
        return Selection(local, local.model_for(task), reason)

    consent_msg = ("Cloud AI needs your consent to send relevant document excerpts to Anthropic. "
                   "Enable it in Settings > AI & Privacy.")
    if mode == "local_only":
        if local_ok:
            return use_local("Local-only mode")
        detail = lh.detail if not lh.available else f"Vision model not installed locally ({local.model_for('vision')})."
        raise AIUnavailableError(f"Local-only mode is selected but the local model is unavailable: {detail}",
                                 code="local_unavailable")
    if mode == "cloud_only":
        if not ch.configured:
            raise AIUnavailableError(f"Cloud-only mode is selected but Claude is not configured: {ch.detail}",
                                     code="not_configured")
        if not cloud_consent:
            raise AIUnavailableError(consent_msg, code="consent_required")
        if not ch.available:
            raise AIUnavailableError(f"Claude is unavailable: {ch.detail}", code="cloud_unavailable")
        return use_cloud("Cloud-only mode")

    # auto
    if task == "simple":
        if local_ok:
            return use_local("Auto: simple task routed to local model")
        if cloud_ok:
            return use_cloud("Auto: local model unavailable, used Claude")
    else:
        if cloud_ok:
            return use_cloud("Auto: advanced task routed to Claude")
        if local_ok:
            reason = "Auto: Claude unavailable" if ch.configured and cloud_consent else (
                "Auto: no cloud consent" if ch.configured else "Auto: Claude not configured")
            return use_local(reason + ", used local model")
    problems = [f"Claude: {ch.detail if ch.configured else 'not configured (set ANTHROPIC_API_KEY)'}"
                + ("" if cloud_consent or not ch.configured else " - consent not given"),
                f"Local (Ollama): {lh.detail}"]
    raise AIUnavailableError("No AI provider is available. " + " | ".join(problems), code="no_provider",
                             details={"cloud": ch.detail, "local": lh.detail})
