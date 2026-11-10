"""Anthropic Claude provider (cloud).

Billing note: the Claude API is billed separately from Claude.ai Pro/Max
subscriptions. A subscription does NOT include API credits - create an API key
at console.anthropic.com and add billing there.
"""
from __future__ import annotations

import base64
import logging
import time
from typing import Any

from app.core.config import get_settings
from app.core.errors import AIProviderError, AIUnavailableError

from .base import ChatMessage, Completion, LLMProvider, ProviderHealth, StreamResult, TaskKind

log = logging.getLogger(__name__)

FALLBACK_BETA = "server-side-fallback-2026-07-01"


def _map_error(exc: Exception) -> AIProviderError:
    import anthropic

    if isinstance(exc, anthropic.AuthenticationError):
        return AIProviderError("Claude API key is invalid or revoked. Update ANTHROPIC_API_KEY in your .env file.",
                               code="invalid_credentials", status_code=502)
    if isinstance(exc, anthropic.PermissionDeniedError):
        return AIProviderError("The Claude API key lacks permission for this model.", code="permission_denied")
    if isinstance(exc, anthropic.NotFoundError):
        return AIProviderError(f"Claude model not found or unavailable: {exc}", code="model_unavailable")
    if isinstance(exc, anthropic.RateLimitError):
        retry = exc.response.headers.get("retry-after") if getattr(exc, "response", None) is not None else None
        return AIProviderError(f"Claude API rate limit reached. Retry in {retry or 'a few'} seconds.",
                               code="rate_limited", status_code=429, details={"retry_after": retry})
    if isinstance(exc, anthropic.APITimeoutError):
        return AIProviderError("The Claude API request timed out.", code="timeout", status_code=504)
    if isinstance(exc, anthropic.APIConnectionError):
        return AIProviderError("Could not reach the Claude API (network problem).", code="network_error")
    if isinstance(exc, anthropic.BadRequestError):
        msg = getattr(exc, "message", str(exc))
        if "credit" in msg.lower() or "billing" in msg.lower():
            return AIProviderError("Your Anthropic API account has insufficient credits. Add billing at "
                                   "console.anthropic.com (a Claude Pro subscription does not include API credits).",
                                   code="billing")
        return AIProviderError(f"Claude rejected the request: {msg}", code="bad_request")
    if isinstance(exc, anthropic.APIStatusError):
        return AIProviderError(f"Claude API error ({exc.status_code}).", code="provider_error")
    return AIProviderError(f"Claude request failed: {exc}", code="provider_error")


def _to_api_messages(messages: list[ChatMessage]) -> list[dict[str, Any]]:
    out = []
    for m in messages:
        if m.images:
            content: list[dict[str, Any]] = [
                {"type": "image", "source": {"type": "base64", "media_type": img.mime_type,
                                             "data": base64.standard_b64encode(img.data).decode()}}
                for img in m.images]
            content.append({"type": "text", "text": m.content})
            out.append({"role": m.role, "content": content})
        else:
            out.append({"role": m.role, "content": m.content})
    return out


class AnthropicProvider(LLMProvider):
    name = "anthropic"
    kind = "cloud"

    def __init__(self) -> None:
        self._client = None
        self._health: tuple[float, ProviderHealth] | None = None

    @property
    def client(self):
        s = get_settings()
        if not s.anthropic_configured:
            raise AIUnavailableError("Claude API is not configured. Set ANTHROPIC_API_KEY in the backend .env file.",
                                     code="not_configured")
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(api_key=s.anthropic_api_key, timeout=s.anthropic_timeout_seconds,
                                               max_retries=2)
        return self._client

    def model_for(self, task: TaskKind) -> str:
        s = get_settings()
        return s.anthropic_fast_model if task == "simple" else s.anthropic_model

    def health(self, force: bool = False) -> ProviderHealth:
        s = get_settings()
        models = {"explain": s.anthropic_model, "vision": s.anthropic_model, "simple": s.anthropic_fast_model,
                  "generate": s.anthropic_model}
        if not s.anthropic_configured:
            return ProviderHealth(self.name, "cloud", False, False,
                                  "Not configured: set ANTHROPIC_API_KEY (API usage is billed separately from "
                                  "Claude subscriptions).", models)
        if self._health and not force and time.monotonic() - self._health[0] < 120:
            return self._health[1]
        try:
            self.client.models.retrieve(s.anthropic_model)  # free metadata call, validates key + model
            h = ProviderHealth(self.name, "cloud", True, True, "Connected", models)
        except Exception as exc:
            err = _map_error(exc)
            h = ProviderHealth(self.name, "cloud", True, False, err.message, models)
        self._health = (time.monotonic(), h)
        return h

    def _params(self, system: str, messages: list[ChatMessage], model: str, max_tokens: int,
                output_format: dict | None = None) -> dict[str, Any]:
        s = get_settings()
        output_config: dict[str, Any] = {"effort": s.anthropic_effort}
        if output_format:
            output_config["format"] = output_format
        params: dict[str, Any] = dict(model=model, max_tokens=max_tokens, system=system,
                                      messages=_to_api_messages(messages), output_config=output_config)
        if not model.startswith("claude-haiku"):
            params["thinking"] = {"type": "adaptive"}
        return params

    def _use_fallbacks(self, model: str) -> bool:
        return get_settings().anthropic_enable_fallbacks and model.startswith(("claude-opus-5", "claude-sonnet-5-5",
                                                                                "claude-fable-5"))

    @staticmethod
    def _text(msg) -> str:
        return "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")

    def complete(self, *, system: str, messages: list[ChatMessage], model: str, max_tokens: int = 16000,
                 json_schema: dict | None = None) -> Completion:
        fmt = {"type": "json_schema", "schema": json_schema} if json_schema else None
        params = self._params(system, messages, model, max_tokens, fmt)
        try:
            if self._use_fallbacks(model):
                stream_ctx = self.client.beta.messages.stream(**params, betas=[FALLBACK_BETA], fallbacks="default")
            else:
                stream_ctx = self.client.messages.stream(**params)
            with stream_ctx as stream:
                msg = stream.get_final_message()
        except AIUnavailableError:
            raise
        except Exception as exc:
            raise _map_error(exc) from exc
        if msg.stop_reason == "refusal":
            raise AIProviderError("Claude declined this request. Try rephrasing it as an educational question.",
                                  code="refusal")
        return Completion(self._text(msg), self.name, msg.model, _usage(msg), msg.stop_reason)

    def stream(self, *, system: str, messages: list[ChatMessage], model: str, max_tokens: int = 32000) -> StreamResult:
        params = self._params(system, messages, model, max_tokens)

        def gen(result: StreamResult):
            try:
                if self._use_fallbacks(model):
                    ctx = self.client.beta.messages.stream(**params, betas=[FALLBACK_BETA], fallbacks="default")
                else:
                    ctx = self.client.messages.stream(**params)
                with ctx as stream:
                    for text in stream.text_stream:
                        yield text
                    msg = stream.get_final_message()
            except AIUnavailableError:
                raise
            except Exception as exc:
                raise _map_error(exc) from exc
            if msg.stop_reason == "refusal":
                raise AIProviderError("Claude declined this request. Try rephrasing it as an educational question.",
                                      code="refusal")
            result.completion = Completion(self._text(msg), self.name, msg.model, _usage(msg), msg.stop_reason)

        return StreamResult(gen)


def _usage(msg) -> dict[str, Any]:
    u = getattr(msg, "usage", None)
    if not u:
        return {}
    return {"input_tokens": getattr(u, "input_tokens", None), "output_tokens": getattr(u, "output_tokens", None)}
