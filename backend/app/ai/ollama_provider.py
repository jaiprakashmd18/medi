"""Ollama-compatible local model provider (http://localhost:11434)."""
from __future__ import annotations

import base64
import json
import time
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.errors import AIProviderError, AIUnavailableError

from .base import ChatMessage, Completion, LLMProvider, ProviderHealth, StreamResult, TaskKind


class OllamaProvider(LLMProvider):
    name = "ollama"
    kind = "local"

    def __init__(self) -> None:
        self._health: tuple[float, ProviderHealth] | None = None

    def model_for(self, task: TaskKind) -> str:
        s = get_settings()
        return s.ollama_vision_model if task == "vision" else s.ollama_model

    def _base(self) -> str:
        return get_settings().ollama_base_url.rstrip("/")

    def installed_models(self) -> list[str]:
        r = httpx.get(f"{self._base()}/api/tags", timeout=3.0)
        r.raise_for_status()
        return [m.get("name", "") for m in r.json().get("models", [])]

    @staticmethod
    def _has(installed: list[str], model: str) -> bool:
        names = set(installed) | {n.split(":")[0] for n in installed if n.endswith(":latest")}
        return model in names or f"{model}:latest" in installed

    def health(self, force: bool = False) -> ProviderHealth:
        s = get_settings()
        models = {"explain": s.ollama_model, "simple": s.ollama_model, "generate": s.ollama_model,
                  "vision": s.ollama_vision_model}
        if self._health and not force and time.monotonic() - self._health[0] < 15:
            return self._health[1]
        try:
            installed = self.installed_models()
        except Exception:
            h = ProviderHealth(self.name, "local", True, False,
                               f"Ollama is not running at {s.ollama_base_url}. Install Ollama and run "
                               f"'ollama pull {s.ollama_model}'.", models)
        else:
            missing = [m for m in {s.ollama_model, s.ollama_vision_model} if not self._has(installed, m)]
            if not self._has(installed, s.ollama_model):
                h = ProviderHealth(self.name, "local", True, False,
                                   f"Ollama is running but model '{s.ollama_model}' is not installed. "
                                   f"Run: ollama pull {s.ollama_model}", models, installed)
            else:
                detail = "Running"
                if missing:
                    detail += f" (vision model '{s.ollama_vision_model}' not installed - diagram analysis unavailable locally)"
                h = ProviderHealth(self.name, "local", True, True, detail, models, installed)
        self._health = (time.monotonic(), h)
        return h

    def vision_available(self) -> bool:
        h = self.health()
        return h.available and self._has(h.installed_models, get_settings().ollama_vision_model)

    @staticmethod
    def _messages(system: str, messages: list[ChatMessage]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = [{"role": "system", "content": system}]
        for m in messages:
            d: dict[str, Any] = {"role": m.role, "content": m.content}
            if m.images:
                d["images"] = [base64.b64encode(i.data).decode() for i in m.images]
            out.append(d)
        return out

    def _post(self, payload: dict[str, Any], stream: bool):
        s = get_settings()
        try:
            client = httpx.Client(timeout=httpx.Timeout(s.ollama_timeout_seconds, connect=5.0))
            req = client.build_request("POST", f"{self._base()}/api/chat", json=payload)
            resp = client.send(req, stream=stream)
        except httpx.ConnectError as exc:
            raise AIUnavailableError(f"Ollama is not reachable at {s.ollama_base_url}. Is it running?",
                                     code="local_unavailable") from exc
        except httpx.TimeoutException as exc:
            raise AIProviderError("The local model timed out.", code="timeout", status_code=504) from exc
        if resp.status_code == 404:
            resp.read()
            raise AIProviderError(f"Local model '{payload['model']}' is not installed. Run: ollama pull {payload['model']}",
                                  code="model_unavailable")
        if resp.status_code >= 400:
            resp.read()
            raise AIProviderError(f"Ollama error {resp.status_code}: {resp.text[:300]}", code="provider_error")
        return client, resp

    def complete(self, *, system: str, messages: list[ChatMessage], model: str, max_tokens: int = 8000,
                 json_schema: dict | None = None) -> Completion:
        payload: dict[str, Any] = {"model": model, "messages": self._messages(system, messages), "stream": False,
                                   "options": {"num_predict": max_tokens, "num_ctx": 16384}}
        if json_schema:
            payload["format"] = json_schema
        client, resp = self._post(payload, stream=False)
        try:
            data = resp.json()
        finally:
            client.close()
        text = data.get("message", {}).get("content", "")
        return Completion(text, self.name, data.get("model", model),
                          {"input_tokens": data.get("prompt_eval_count"), "output_tokens": data.get("eval_count")},
                          data.get("done_reason"))

    def stream(self, *, system: str, messages: list[ChatMessage], model: str, max_tokens: int = 8000) -> StreamResult:
        payload = {"model": model, "messages": self._messages(system, messages), "stream": True,
                   "options": {"num_predict": max_tokens, "num_ctx": 16384}}

        def gen(result: StreamResult):
            client, resp = self._post(payload, stream=True)
            parts: list[str] = []
            final: dict[str, Any] = {}
            try:
                for line in resp.iter_lines():
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    if data.get("error"):
                        raise AIProviderError(f"Local model error: {data['error']}", code="provider_error")
                    piece = data.get("message", {}).get("content", "")
                    if piece:
                        parts.append(piece)
                        yield piece
                    if data.get("done"):
                        final = data
            except httpx.TimeoutException as exc:
                raise AIProviderError("The local model timed out.", code="timeout", status_code=504) from exc
            finally:
                resp.close()
                client.close()
            result.completion = Completion("".join(parts), self.name, final.get("model", model),
                                           {"input_tokens": final.get("prompt_eval_count"),
                                            "output_tokens": final.get("eval_count")}, final.get("done_reason"))

        return StreamResult(gen)
