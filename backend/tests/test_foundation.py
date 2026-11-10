"""Phase 1 acceptance: app boots, DB migrates, health + providers + settings work."""


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"]["ok"] is True
    assert body["checks"]["vector_store"]["ok"] is True


def test_providers_report_unconfigured_honestly(client):
    r = client.get("/api/ai/providers")
    assert r.status_code == 200
    body = r.json()
    names = {p["name"]: p for p in body["providers"]}
    assert names["anthropic"]["configured"] is False
    assert names["ollama"]["available"] is False
    assert body["routes"]["explain"]["ok"] is False
    assert "billed separately" in body["billing_note"]


def test_builtin_subjects_seeded(client):
    names = [s["name"] for s in client.get("/api/subjects").json()]
    for expected in ("Anatomy", "Histology", "Physiology", "Pharmacology", "Clinical Medicine", "Medical Biophysics"):
        assert expected in names


def test_custom_subject_and_conflict(client):
    r = client.post("/api/subjects", json={"name": "Embryology", "color": "#123456"})
    assert r.status_code == 201
    assert r.json()["is_custom"] is True
    r2 = client.post("/api/subjects", json={"name": "embryology"})
    assert r2.status_code == 409
    assert r2.json()["error"]["code"] == "conflict"


def test_settings_roundtrip(client):
    r = client.put("/api/settings", json={"default_teaching_level": 4, "ai_mode": "local_only"})
    assert r.status_code == 200
    assert r.json()["default_teaching_level"] == 4
    assert client.get("/api/settings").json()["ai_mode"] == "local_only"
    client.put("/api/settings", json={"default_teaching_level": 2, "ai_mode": "auto"})


def test_validation_errors_are_structured(client):
    r = client.put("/api/settings", json={"default_teaching_level": 9})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_failed"


def test_unknown_route_structured_404(client):
    r = client.get("/api/documents/doesnotexist")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"
