"""NVIDIA Nemotron reranking: policy/consent, isolation, fallback, citations, scoring.

A local HTTP server stands in for the NVIDIA endpoint (test double), so the real
httpx request/response code path is exercised without network access or a key.
"""
from __future__ import annotations

import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.core.config import get_settings
from app.rag import nvidia_reranker
from app.rag.nvidia_reranker import RerankUnavailable, _parse

from .conftest import upload, wait_ready

FAKE_KEY = "nvapi-TESTKEY-0123456789abcdef"


class FakeNvidia(BaseHTTPRequestHandler):
    mode = "ok"        # ok | timeout | 429 | 401 | 500 | malformed | partial | notjson
    prefer = ""        # substring: passages containing it get the highest logit
    logit_boost = 0.0  # added to every logit (to prove logits never decide sufficiency)
    requests: list[dict] = []

    def log_message(self, *a):
        pass

    def _send(self, code, body, headers=None):
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeNvidia.requests.append({"body": body, "auth": self.headers.get("Authorization")})
        m = FakeNvidia.mode
        if m == "timeout":
            time.sleep(1.5)
            return self._send(200, {"rankings": []})
        if m == "429":
            return self._send(429, {"detail": "rate limited"}, {"Retry-After": "30"})
        if m == "401":
            return self._send(401, {"detail": "unauthorized"})
        if m == "500":
            return self._send(500, {"detail": "boom"})
        if m == "notjson":
            return self._send(200, b"<html>gateway</html>")
        passages = body["passages"]
        if m == "malformed":
            return self._send(200, {"rankings": [{"index": len(passages) + 5, "logit": 1.0}]})
        q = set(re.findall(r"[a-z]{4,}", body["query"]["text"].lower()))
        ranks = []
        for i, p in enumerate(passages):
            t = p["text"].lower()
            logit = sum(1 for w in q if w in t) - 5.0 + FakeNvidia.logit_boost
            if FakeNvidia.prefer and FakeNvidia.prefer.lower() in t:
                logit += 100
            ranks.append({"index": i, "logit": logit})
        if m == "partial":
            ranks = ranks[: max(1, len(ranks) // 2)]
        ranks.sort(key=lambda r: r["index"])  # deliberately NOT sorted by score
        return self._send(200, {"rankings": ranks})


@pytest.fixture()
def nvidia(monkeypatch):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeNvidia)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    s = get_settings()
    monkeypatch.setattr(s, "nvidia_api_key", FAKE_KEY)
    monkeypatch.setattr(s, "nvidia_rerank_enabled", True)
    monkeypatch.setattr(s, "nvidia_rerank_url", f"http://127.0.0.1:{srv.server_port}/v1/retrieval/nvidia/rerank")
    monkeypatch.setattr(s, "nvidia_rerank_timeout_seconds", 0.5)
    FakeNvidia.mode, FakeNvidia.prefer, FakeNvidia.logit_boost = "ok", "", 0.0
    FakeNvidia.requests = []
    nvidia_reranker.reset_state()
    yield FakeNvidia
    nvidia_reranker.reset_state()
    srv.shutdown()


@pytest.fixture()
def nv_consent(client):
    client.put("/api/settings", json={"nvidia_consent": True, "ai_mode": "auto"})
    yield
    client.put("/api/settings", json={"nvidia_consent": False, "ai_mode": "auto"})


def _search(client, q, doc_id=None, limit=8):
    params = {"q": q, "limit": limit}
    if doc_id:
        params["document_ids"] = [doc_id]
    r = client.get("/api/search", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _db_chunks(doc_id):
    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models import Chunk

    with SessionLocal() as db:
        return {c.id: c for c in db.scalars(select(Chunk).where(Chunk.document_id == doc_id))}


# ------------------------------------------------------------------ success + citations
def test_successful_rerank_reorders_and_preserves_metadata(client, heart_doc, nvidia, nv_consent):
    client.put("/api/settings", json={"nvidia_consent": False})
    local = _search(client, "cardiac conduction heart ventricle atrium", heart_doc["id"])
    client.put("/api/settings", json={"nvidia_consent": True})
    assert len(local["results"]) >= 3
    last = local["results"][-1]
    nvidia.prefer = last["text"][:60]
    res = _search(client, "cardiac conduction heart ventricle atrium", heart_doc["id"])
    assert res["ranker"] == "nvidia", res["rerank_note"]
    assert res["results"][0]["chunk_id"] == last["chunk_id"]  # promoted from last place
    assert {r["chunk_id"] for r in res["results"]} == {r["chunk_id"] for r in local["results"]}
    # metadata comes from the database, untouched by reranking
    db = _db_chunks(heart_doc["id"])
    title = client.get(f"/api/documents/{heart_doc['id']}").json()["title"]
    for r in res["results"]:
        c = db[r["chunk_id"]]
        assert (r["document_id"], r["page_number"], r["section"], r["text"], r["kind"]) == \
               (c.document_id, c.page_number, c.section, c.text, c.kind)
        assert r["document_title"] == title
    # minimal payload: only query + passage texts, no ids/titles; key sent as bearer token
    req = nvidia.requests[-1]
    assert set(req["body"]) == {"model", "query", "passages", "truncate"}
    assert all(set(p) == {"text"} for p in req["body"]["passages"])
    assert req["body"]["model"] == "nvidia/nemotron-3.5-rerank-8b"
    sent = json.dumps(req["body"])
    assert heart_doc["id"] not in sent, sent[:3000]
    assert req["auth"] == f"Bearer {FAKE_KEY}"


def test_passage_and_query_length_capped(client, heart_doc, nvidia, nv_consent, monkeypatch):
    monkeypatch.setattr(get_settings(), "nvidia_rerank_max_passage_chars", 50)
    monkeypatch.setattr(get_settings(), "nvidia_rerank_max_query_chars", 20)
    _search(client, "the sinoatrial node pacemaker of the heart", heart_doc["id"])
    body = nvidia.requests[-1]["body"]
    assert len(body["query"]["text"]) <= 20
    assert all(len(p["text"]) <= 50 for p in body["passages"])


def test_tutor_citations_follow_reranked_order(client, heart_doc, nvidia, nv_consent, fake_cloud, consent):
    client.put("/api/settings", json={"nvidia_consent": False})
    last = _search(client, "cardiac conduction heart ventricle atrium", heart_doc["id"])["results"][-1]
    client.put("/api/settings", json={"nvidia_consent": True})
    nvidia.prefer = last["text"][:60]
    r = client.post("/api/tutor/chat/stream", json={"message": "cardiac conduction heart ventricle atrium", "document_ids": [heart_doc["id"]]})
    events = [(b.split("\n")[0][7:], json.loads(b.split("\n")[1][6:])) for b in r.text.strip().split("\n\n")]
    meta = events[0][1]
    assert meta["ranker"] == "nvidia"
    assert meta["sources"][0]["chunk_id"] == last["chunk_id"]
    # the prompt numbers sources in the reranked order: [1] is the promoted passage
    prompt = fake_cloud.calls[-1]["messages"][-1].content
    first_src = prompt[prompt.index('<source id="1"'):prompt.index("</source>")]
    assert last["text"][:60] in first_src
    done = events[-1][1]
    assert done["used_citations"] == [1] and done["invalid_citations"] == [99]  # validation unchanged
    conv = client.get(f"/api/tutor/conversations/{meta['conversation_id']}").json()
    msg = conv["messages"][-1]
    assert msg["meta"]["ranker"] == "nvidia"
    cite1 = next(c for c in msg["citations"] if c["label"] == 1)
    db = _db_chunks(heart_doc["id"])
    assert cite1["chunk_id"] == last["chunk_id"] and cite1["page_number"] == db[cite1["chunk_id"]].page_number
    assert cite1["used_in_answer"] is True


# ------------------------------------------------------------------ consent / mode
def test_no_consent_no_request(client, heart_doc, nvidia):
    client.put("/api/settings", json={"nvidia_consent": False})
    res = _search(client, "mitral valve", heart_doc["id"])
    assert res["ranker"] == "local" and "no consent" in res["rerank_note"]
    assert nvidia.requests == []


def test_cloud_consent_alone_is_not_nvidia_consent(client, heart_doc, nvidia, consent):
    res = _search(client, "mitral valve", heart_doc["id"])
    assert res["ranker"] == "local" and nvidia.requests == []


def test_local_only_mode_blocks_nvidia(client, heart_doc, nvidia, nv_consent):
    client.put("/api/settings", json={"ai_mode": "local_only"})
    res = _search(client, "mitral valve", heart_doc["id"])
    assert res["ranker"] == "local" and "local-only" in res["rerank_note"]
    assert nvidia.requests == []


def test_consent_revocation(client, heart_doc, nvidia):
    r = client.put("/api/settings", json={"nvidia_consent": True}).json()
    assert r["nvidia_consent"] is True and r["nvidia_consent_at"]
    assert _search(client, "mitral valve", heart_doc["id"])["ranker"] == "nvidia"
    n = len(nvidia.requests)
    r = client.put("/api/settings", json={"nvidia_consent": False}).json()
    assert r["nvidia_consent"] is False and r["nvidia_consent_at"] is None
    assert _search(client, "mitral valve", heart_doc["id"])["ranker"] == "local"
    assert len(nvidia.requests) == n


def test_not_configured_no_request(client, heart_doc, nvidia, nv_consent, monkeypatch):
    monkeypatch.setattr(get_settings(), "nvidia_api_key", "")
    assert _search(client, "mitral valve", heart_doc["id"])["ranker"] == "local"
    monkeypatch.setattr(get_settings(), "nvidia_api_key", FAKE_KEY)
    monkeypatch.setattr(get_settings(), "nvidia_rerank_enabled", False)
    assert _search(client, "mitral valve", heart_doc["id"])["ranker"] == "local"
    assert nvidia.requests == []


# ------------------------------------------------------------------ isolation
def test_other_users_documents_never_sent(client, heart_doc, fixtures_dir, nvidia, monkeypatch, tmp_path):
    import pymupdf

    secret = "ZEBRAFISH-CONFIDENTIAL cardiac valve notes belonging to another student"
    pdf = tmp_path / "other.pdf"
    d = pymupdf.open()
    d.new_page().insert_textbox(pymupdf.Rect(72, 72, 540, 400), (secret + ". ") * 8, fontsize=11)
    d.save(str(pdf))
    monkeypatch.setattr(get_settings(), "auth_mode", "multi_user")
    tok = client.post("/api/auth/register", json={"email": "other@uni.edu", "password": "longpassword1"}).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    r = client.post("/api/documents/upload", files=[("files", ("other.pdf", pdf.read_bytes()))], headers=h)
    other_id = r.json()["documents"][0]["id"]
    for _ in range(100):
        if client.get(f"/api/documents/{other_id}/status", headers=h).json()["status"] in ("ready", "partial", "failed"):
            break
        time.sleep(0.2)
    monkeypatch.setattr(get_settings(), "auth_mode", "single_user")
    client.put("/api/settings", json={"nvidia_consent": True})
    try:
        res = _search(client, "cardiac valve notes the heart")  # library-wide search, default user
        assert res["ranker"] == "nvidia"
        sent = json.dumps([q["body"] for q in nvidia.requests])
        assert "ZEBRAFISH" not in sent
        assert all(x["document_id"] != other_id for x in res["results"])
        # document-scoped search sends only that document's passages
        nvidia.requests.clear()
        _search(client, "the heart", heart_doc["id"])
        own = {c.text[:2000] for c in _db_chunks(heart_doc["id"]).values()}
        assert all(p["text"] in own for p in nvidia.requests[-1]["body"]["passages"])
    finally:
        client.put("/api/settings", json={"nvidia_consent": False})


def test_empty_results_make_no_request(client, nvidia, nv_consent):
    res = _search(client, "anything", "nonexistent-document")
    assert res["results"] == [] and nvidia.requests == []


# ------------------------------------------------------------------ failures -> fallback
@pytest.mark.parametrize("mode,code", [("timeout", "timed out"), ("429", "rate limit"), ("401", "rejected"),
                                       ("500", "service error"), ("malformed", "invalid passage index"),
                                       ("notjson", "non-JSON")])
def test_failures_fall_back_to_local_order(client, heart_doc, nvidia, nv_consent, mode, code):
    client.put("/api/settings", json={"nvidia_consent": False})
    local = _search(client, "mitral valve", heart_doc["id"])
    client.put("/api/settings", json={"nvidia_consent": True})
    nvidia.mode = mode
    res = _search(client, "mitral valve", heart_doc["id"])
    assert res["ranker"] == "local"
    assert code in res["rerank_note"] and "Used local ranking" in res["rerank_note"]
    assert [r["chunk_id"] for r in res["results"]] == [r["chunk_id"] for r in local["results"]]
    assert FAKE_KEY not in json.dumps(res)


def test_rate_limit_cooldown_skips_calls(client, heart_doc, nvidia, nv_consent):
    nvidia.mode = "429"
    _search(client, "mitral valve", heart_doc["id"])
    n = len(nvidia.requests)
    nvidia.mode = "ok"
    res = _search(client, "mitral valve", heart_doc["id"])
    assert len(nvidia.requests) == n and "paused" in res["rerank_note"]
    assert nvidia_reranker.cooldown_remaining() > 20  # Retry-After: 30 honoured
    nvidia_reranker.reset_state()
    assert _search(client, "mitral valve", heart_doc["id"])["ranker"] == "nvidia"


def test_partial_rankings_keep_unranked_in_local_order(client, heart_doc, nvidia, nv_consent):
    nvidia.mode = "partial"
    res = _search(client, "cardiac conduction heart ventricle atrium", heart_doc["id"], limit=10)
    assert res["ranker"] == "nvidia" and len(res["results"]) >= 2


# ------------------------------------------------------------------ scoring / sufficiency
def test_logits_do_not_decide_sufficiency(client, heart_doc, nvidia, nv_consent):
    nvidia.logit_boost = 1e6  # absurdly confident reranker
    for q in ("mitral valve", "renal glomerular filtration in the kidney nephron",
              "quantum chromodynamics gluon confinement"):
        client.put("/api/settings", json={"nvidia_consent": False})
        local = _search(client, q, heart_doc["id"])
        client.put("/api/settings", json={"nvidia_consent": True})
        res = _search(client, q, heart_doc["id"])
        best = max((r["score"] for r in res["results"]), default=0.0)
        assert res["sufficient"] == (bool(res["results"]) and best >= get_settings().retrieval_min_score)
        if not local["results"]:
            assert res["results"] == []  # reranking cannot add filtered-out passages
        if not local["sufficient"]:
            assert res["sufficient"] is False  # a confident reranker cannot manufacture evidence


def test_page_focus_is_kept_after_rerank(client, heart_doc, nvidia, nv_consent, fake_cloud, consent):
    nvidia.prefer = "mitral"  # reranker prefers page 1 content
    client.post("/api/tutor/explain", json={"document_id": heart_doc["id"], "page_number": 3, "action": "simple"})
    prompt = fake_cloud.calls[-1]["messages"][-1].content
    assert 'location="page 3"' in prompt


@pytest.mark.parametrize("body", [None, [], {"rankings": "x"}, {"rankings": []}, {"rankings": [{"index": 0}]},
                                  {"rankings": [{"index": "0", "logit": 1}]}, {"rankings": [{"index": 0, "logit": "nan"}]},
                                  {"rankings": [{"index": 0, "logit": 1}, {"index": 0, "logit": 2}]},
                                  {"rankings": [{"index": -1, "logit": 1}]},
                                  {"rankings": [{"index": 0, "logit": float("inf")}]}])
def test_parse_rejects_malformed(body):
    with pytest.raises(RerankUnavailable):
        _parse(body, 3)


def test_parse_sorts_by_logit_and_accepts_negative():
    out = _parse({"rankings": [{"index": 0, "logit": -3.2}, {"index": 2, "logit": 4.1}, {"index": 1, "logit": -0.5}]}, 3)
    assert [r.index for r in out] == [2, 1, 0]


# ------------------------------------------------------------------ secrets / status
def test_key_never_exposed(client, heart_doc, nvidia, nv_consent, caplog):
    nvidia.mode = "401"
    with caplog.at_level("DEBUG"):
        res = _search(client, "mitral valve", heart_doc["id"])
    prov = client.get("/api/ai/providers").json()
    sett = client.get("/api/settings").json()
    for blob in (json.dumps(res), json.dumps(prov), json.dumps(sett), caplog.text):
        assert FAKE_KEY not in blob
    assert prov["reranker"]["configured"] is True and prov["reranker"]["active_for_you"] is True
    from app.core.logging import redact

    assert FAKE_KEY not in redact(f"Authorization: Bearer {FAKE_KEY}")


# ------------------------------------------------------------------ evaluation harness
def test_evaluation_harness_compares_rankers():
    from app.rag.evaluation import evaluate, format_report, load_eval, local_ranker
    from app.rag.vectorstore import hashing_embedder

    data = load_eval()
    assert len(data["questions"]) >= 10
    ids = {p["id"] for p in data["passages"]}
    assert all(set(q["relevant"]) <= ids for q in data["questions"])
    base = evaluate("local", local_ranker(hashing_embedder), data)
    assert 0.5 <= base.mrr <= 1.0  # regression floor for the offline baseline

    rel = {q["q"]: q["relevant"] for q in data["questions"]}

    def oracle(q, passages):  # perfect reranker: proves the metrics are computed correctly
        return rel[q] + [p["id"] for p in passages if p["id"] not in rel[q]]

    best = evaluate("oracle", oracle, data)
    assert (best.hit_at_1, best.recall_at_3, best.mrr) == (1.0, 1.0, 1.0)
    assert "| local |" in format_report([base, best])


def test_evaluation_with_mocked_nvidia(nvidia):
    from app.rag.evaluation import evaluate, load_eval, nvidia_ranker

    data = load_eval()
    m = evaluate("nvidia(mock)", nvidia_ranker(), data)
    assert len(nvidia.requests) == len(data["questions"])
    assert 0.0 <= m.mrr <= 1.0
