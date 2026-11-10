"""Test configuration.

Tests run against a temporary data directory with a deterministic offline
embedder (EMBEDDING_BACKEND=hashing). AI calls go to ``FakeProvider``, a test
double that produces deterministic outputs in the same formats the real
providers return. It is only registered by tests; the application never uses
canned answers.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="medigenius-test-"))
os.environ.update({"DATA_DIR": str(_TMP / "data"), "EMBEDDING_BACKEND": "hashing", "APP_ENV": "test",
                   "ANTHROPIC_API_KEY": "", "OLLAMA_BASE_URL": "http://127.0.0.1:9", "AUTH_MODE": "single_user"})

from app.ai.base import Completion, LLMProvider, ProviderHealth, StreamResult  # noqa: E402

from . import fixtures_gen  # noqa: E402


class FakeProvider(LLMProvider):
    def __init__(self, name="anthropic", kind="cloud", available=True):
        self.name, self.kind, self.available = name, kind, available
        self.calls: list[dict] = []
        self.answer_template = "From your documents: the mitral valve lies between the left atrium and ventricle [1]." \
                               "\n\n### Additional explanation (AI-generated)\nThink of valves as one-way doors. [99]"
        self.quiz_override: dict | None = None

    def health(self, force=False):
        return ProviderHealth(self.name, self.kind, True, self.available, "fake", {"explain": "fake-model"})

    def model_for(self, task):
        return f"fake-{task}"

    def vision_available(self):
        return self.available

    def complete(self, *, system, messages, model, max_tokens=8000, json_schema=None):
        self.calls.append({"system": system, "messages": messages, "model": model, "schema": json_schema})
        prompt = messages[-1].content
        n_sources = len(re.findall(r'<source id="\d+"', prompt))
        if json_schema and "questions" in json_schema.get("properties", {}):
            data = self.quiz_override or {"questions": [
                {"type": "sba", "prompt": "Which valve lies between the left atrium and left ventricle?",
                 "options": ["Tricuspid", "Mitral", "Pulmonary", "Aortic", "Eustachian"], "correct_options": [1],
                 "true_false_answer": "n/a", "accepted_answers": [], "model_answer": "", "key_points": [],
                 "explanation": "The mitral valve [1].", "topic": "Heart valves", "source_ids": [1], "image_ref": ""},
                {"type": "true_false", "prompt": "The SA node is located in the wall of the right atrium.",
                 "options": [], "correct_options": [], "true_false_answer": "true", "accepted_answers": [],
                 "model_answer": "", "key_points": [], "explanation": "Stated in the source.", "topic": "Conduction",
                 "source_ids": [min(2, n_sources)], "image_ref": ""},
                {"type": "fill_blank", "prompt": "The natural pacemaker of the heart is the _____ node.",
                 "options": [], "correct_options": [], "true_false_answer": "n/a", "accepted_answers": ["sinoatrial", "SA"],
                 "model_answer": "", "key_points": [], "explanation": "SA node.", "topic": "Conduction",
                 "source_ids": [1], "image_ref": ""},
                {"type": "short", "prompt": "Explain why the left ventricle has the thickest wall.", "options": [],
                 "correct_options": [], "true_false_answer": "n/a", "accepted_answers": [],
                 "model_answer": "Because it generates high pressure to perfuse the systemic circulation.",
                 "key_points": ["high pressure", "systemic circulation"], "explanation": "", "topic": "Heart valves",
                 "source_ids": [1], "image_ref": ""},
                # invalid: cites a source that does not exist -> must be rejected
                {"type": "sba", "prompt": "Unsupported question about the kidneys?", "options": ["A", "B", "C", "D"],
                 "correct_options": [0], "true_false_answer": "n/a", "accepted_answers": [], "model_answer": "",
                 "key_points": [], "explanation": "", "topic": "Renal", "source_ids": [999], "image_ref": ""},
            ]}
            return Completion(json.dumps(data), self.name, model)
        if json_schema and "cards" in json_schema.get("properties", {}):
            return Completion(json.dumps({"cards": [
                {"front": "What is the rate-limiting enzyme of glycolysis?", "back": "Phosphofructokinase-1.",
                 "topic": "Glycolysis", "source_id": 1},
                {"front": "Bad card", "back": "no source", "topic": "x", "source_id": 0}]}), self.name, model)
        if json_schema and "grades" in json_schema.get("properties", {}):
            idx = [int(i) for i in re.findall(r'<item index="(\d+)"', prompt)]
            return Completion(json.dumps({"grades": [{"question_index": i, "score": 0.8, "feedback": "Good.",
                                                      "missing_points": []} for i in idx]}), self.name, model)
        return Completion("Diagram explanation: shows the Aorta and Left Ventricle [1].", self.name, model)

    def stream(self, *, system, messages, model, max_tokens=16000):
        self.calls.append({"system": system, "messages": messages, "model": model})
        text = self.answer_template

        def gen(result: StreamResult):
            for i in range(0, len(text), 20):
                yield text[i:i + 20]
            result.completion = Completion(text, self.name, model + "-served", {"output_tokens": 10}, "end_turn")

        return StreamResult(gen)


@pytest.fixture(scope="session")
def fixtures_dir():
    d = _TMP / "fixtures"
    d.mkdir(exist_ok=True)
    fixtures_gen.make_pdf(d / "heart.pdf")
    fixtures_gen.make_pdf(d / "injected.pdf", injection=True)
    fixtures_gen.make_pptx(d / "plexus.pptx")
    fixtures_gen.make_docx(d / "glycolysis.docx")
    fixtures_gen.make_png(d / "diagram.png")
    return d


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def fake_cloud():
    from app.ai import router

    fake = FakeProvider("anthropic", "cloud", True)
    router.set_provider("anthropic", fake)
    router.set_provider("ollama", FakeProvider("ollama", "local", False))
    yield fake
    router.reset_providers()


@pytest.fixture()
def consent(client):
    client.put("/api/settings", json={"cloud_consent": True, "ai_mode": "auto"})
    yield
    client.put("/api/settings", json={"cloud_consent": False, "ai_mode": "auto"})


def wait_ready(client, doc_id, timeout=60):
    import time

    t0 = time.time()
    while time.time() - t0 < timeout:
        st = client.get(f"/api/documents/{doc_id}/status").json()
        if st["status"] in ("ready", "partial", "failed"):
            return st
        time.sleep(0.2)
    raise AssertionError(f"document {doc_id} did not finish processing")


def upload(client, path: Path, **form):
    with open(path, "rb") as f:
        r = client.post("/api/documents/upload", files=[("files", (path.name, f.read()))], data=form)
    assert r.status_code == 201, r.text
    doc = r.json()["documents"][0]
    wait_ready(client, doc["id"])
    return client.get(f"/api/documents/{doc['id']}").json()


@pytest.fixture(scope="session")
def heart_doc(client, fixtures_dir):
    return upload(client, fixtures_dir / "heart.pdf")


def pytest_sessionfinish(session, exitstatus):
    from app.processing.jobs import reset_queue

    reset_queue()
    shutil.rmtree(_TMP, ignore_errors=True)
