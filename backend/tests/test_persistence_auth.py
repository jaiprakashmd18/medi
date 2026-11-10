"""Persistence across restarts + multi-user authorization."""
from fastapi.testclient import TestClient


def test_data_survives_restart(client, heart_doc):
    from app.main import create_app
    from app.rag.vectorstore import reset_vector_store

    before = client.get("/api/documents").json()
    reset_vector_store()  # simulate process restart of the vector index
    with TestClient(create_app()) as c2:
        after = c2.get("/api/documents").json()
        assert {d["id"] for d in before} == {d["id"] for d in after}
        r = c2.get("/api/search", params={"q": "sinoatrial node pacemaker", "document_ids": [heart_doc["id"]]})
        assert r.json()["results"], "vector index did not persist"


def test_multi_user_isolation(client, heart_doc, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "auth_mode", "multi_user")
    assert client.get("/api/documents").status_code == 401
    r = client.post("/api/auth/register", json={"email": "a@uni.edu", "password": "correct horse", "display_name": "A"})
    assert r.status_code == 201
    token = r.json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/auth/me", headers=h).json()["email"] == "a@uni.edu"
    # user A cannot see the default user's document
    assert client.get(f"/api/documents/{heart_doc['id']}", headers=h).status_code == 404
    assert client.get("/api/documents", headers=h).json() == []
    assert client.get("/api/search", params={"q": "heart valve"}, headers=h).json()["results"] == []
    bad = client.post("/api/auth/login", json={"email": "a@uni.edu", "password": "wrong"})
    assert bad.status_code == 401
    assert client.get("/api/documents", headers={"Authorization": "Bearer forged.token"}).status_code == 401


def test_secret_redaction():
    from app.core.logging import redact

    assert "sk-ant-abc" not in redact("key=sk-ant-abcdef1234567890 x")
    assert "***REDACTED***" in redact('{"x-api-key": "supersecret"}')


def test_access_token_redacted_in_logs():
    from app.core.logging import redact

    assert "abc.def" not in redact('GET /api/documents/x/file?access_token=abc.def HTTP/1.1')


def test_cannot_attach_foreign_subject(client, heart_doc):
    r = client.patch(f"/api/documents/{heart_doc['id']}", json={"subject_id": 99999})
    assert r.status_code == 404
