"""Phases 5-6 acceptance: quizzes, grading, progress, flashcards, spaced repetition."""
from datetime import timedelta

from app.models import Flashcard, utcnow
from app.revision.srs import schedule

from .conftest import upload


def test_quiz_requires_provider(client, heart_doc):
    from app.ai import router

    router.reset_providers()
    r = client.post("/api/quizzes/generate", json={"document_ids": [heart_doc["id"]], "num_questions": 3})
    assert r.status_code == 503


def test_quiz_generate_submit_and_progress(client, heart_doc, fake_cloud, consent):
    r = client.post("/api/quizzes/generate", json={
        "document_ids": [heart_doc["id"]], "num_questions": 5, "difficulty": "medium",
        "question_types": ["sba", "true_false", "fill_blank", "short"]})
    assert r.status_code == 201, r.text
    quiz = r.json()
    assert len(quiz["questions"]) == 4  # the unsupported question was rejected
    assert any("no valid supporting source" in w for w in quiz["warnings"])
    # answers are not leaked before submission
    assert "correct_answer" not in quiz["questions"][0]
    answers = {"0": 0, "1": True, "2": "Sinoatrial", "3": "It pumps at high pressure into the systemic circulation."}
    res = client.post(f"/api/quizzes/{quiz['id']}/submit", json={"answers": answers}).json()
    by_idx = {x["question_index"]: x for x in res["results"]}
    assert by_idx[0]["correct"] is False  # chose Tricuspid
    assert by_idx[1]["correct"] is True
    assert by_idx[2]["correct"] is True
    assert by_idx[3]["grading"] == "ai" and by_idx[3]["score"] == 0.8
    assert by_idx[0]["citations"][0]["page_number"] >= 1
    assert res["max_score"] == 4 and 0 < res["percent"] < 100
    assert any(t["topic"] == "Heart valves" for t in res["topic_breakdown"])
    assert res["recommendations"]
    results = client.get(f"/api/quizzes/{quiz['id']}/results").json()
    assert len(results["attempts"]) == 1
    # mistakes became flashcards
    cards = client.get("/api/revision/cards").json()
    assert any(c["origin"] == "quiz_mistake" and "left atrium" in c["front"] for c in cards)
    prog = client.get("/api/progress").json()
    assert any(t["name"] == "Conduction" for t in prog["topics"])
    assert prog["quiz_history"] and "not a measure of clinical competence" in prog["disclaimer"]


def test_written_answer_fallback_estimate(client, heart_doc, fake_cloud, consent):
    quiz = client.post("/api/quizzes/generate", json={"document_ids": [heart_doc["id"]], "num_questions": 4,
                                                      "question_types": ["short", "sba"]}).json()
    from app.ai import router

    router.reset_providers()  # AI grading unavailable now
    idx = next(q["index"] for q in quiz["questions"] if q["type"] == "short")
    res = client.post(f"/api/quizzes/{quiz['id']}/submit",
                      json={"answers": {str(idx): "Because of high pressure for the systemic circulation"}}).json()
    r = next(x for x in res["results"] if x["question_index"] == idx)
    assert r["grading"] == "keyword_estimate" and "ESTIMATE" in r["feedback"]


def test_quiz_rejects_malformed_questions():
    from app.exams.generator import validate_question

    base = {"options": [], "correct_options": [], "true_false_answer": "n/a", "accepted_answers": [],
            "model_answer": "", "key_points": [], "explanation": "", "topic": "t", "source_ids": [1], "image_ref": ""}
    bad_sba = {**base, "type": "sba", "prompt": "Which is right here?", "options": ["a", "b", "c", "d"],
               "correct_options": [0, 1]}
    assert validate_question(bad_sba, 3, {"sba"}, {})[0] is None
    aota = {**base, "type": "sba", "prompt": "Which is right here?", "options": ["a", "b", "c", "All of the above"],
            "correct_options": [3]}
    assert validate_question(aota, 3, {"sba"}, {})[0] is None
    fb = {**base, "type": "fill_blank", "prompt": "No blank in this prompt", "accepted_answers": ["x"]}
    assert validate_question(fb, 3, {"fill_blank"}, {})[0] is None


def test_flashcards_generate_and_review(client, fixtures_dir, fake_cloud, consent):
    d = upload(client, fixtures_dir / "glycolysis.docx")
    r = client.post("/api/revision/generate", json={"document_ids": [d["id"]], "count": 5})
    assert r.status_code == 201, r.text
    body = r.json()
    assert len(body["cards"]) == 1 and body["warnings"]  # card without source rejected
    card = body["cards"][0]
    assert card["citation"]["document_id"] == d["id"]
    due = client.get("/api/revision").json()
    assert any(c["id"] == card["id"] for c in due["due"])
    rv = client.post(f"/api/revision/cards/{card['id']}/review", json={"rating": 2}).json()
    assert rv["repetitions"] == 1 and rv["interval_days"] == 1
    due2 = client.get("/api/revision").json()
    assert not any(c["id"] == card["id"] for c in due2["due"])
    assert due2["stats"]["reviewed_today"] >= 1


def test_manual_flashcard_crud(client):
    c = client.post("/api/revision/cards", json={"front": "Q", "back": "A", "topic": "Manual"}).json()
    assert c["origin"] == "manual"
    assert client.patch(f"/api/revision/cards/{c['id']}", json={"suspended": True}).json()["suspended"] is True
    assert client.delete(f"/api/revision/cards/{c['id']}").status_code == 204


def test_sm2_schedule():
    c = Flashcard(user_id="u", front="f", back="b", ease=2.5, interval_days=0, repetitions=0, lapses=0, due_at=utcnow())
    schedule(c, 2)
    assert c.interval_days == 1
    schedule(c, 2)
    assert c.interval_days == 6
    schedule(c, 3)
    assert c.interval_days > 15
    schedule(c, 0)
    assert c.repetitions == 0 and c.lapses == 1 and c.interval_days < 0.01
    assert c.due_at - utcnow() < timedelta(minutes=11)


def test_topic_manual_status(client):
    t = client.post("/api/topics", json={"name": "Brachial plexus"}).json()
    t2 = client.patch(f"/api/topics/{t['id']}", json={"status": "mastered"}).json()
    assert t2["status"] == "mastered" and t2["status_manual"] is True


def test_dashboard_and_export(client, heart_doc):
    dash = client.get("/api/dashboard").json()
    assert dash["recent_documents"]
    client.post(f"/api/documents/{heart_doc['id']}/viewed", json={"page_number": 2})
    dash = client.get("/api/dashboard").json()
    assert dash["continue_learning"][0]["last_page_viewed"] == 2
    r = client.get("/api/export")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    import io
    import json
    import zipfile

    data = json.loads(zipfile.ZipFile(io.BytesIO(r.content)).read("medi-genius-export.json"))
    assert data["documents"] and "password_hash" not in json.dumps(data["user"])


def test_explanation_citations_renumbered(client, heart_doc, fake_cloud, consent):
    fake_cloud.quiz_override = {"questions": [
        {"type": "sba", "prompt": "Which valve lies between the left atrium and ventricle?",
         "options": ["Tricuspid", "Mitral", "Pulmonary", "Aortic"], "correct_options": [1], "true_false_answer": "n/a",
         "accepted_answers": [], "model_answer": "", "key_points": [], "explanation": "See [2] and [7].",
         "topic": "Valves", "source_ids": [2], "image_ref": ""}]}
    quiz = client.post("/api/quizzes/generate", json={"document_ids": [heart_doc["id"]], "num_questions": 1}).json()
    res = client.post(f"/api/quizzes/{quiz['id']}/submit", json={"answers": {"0": 1}}).json()
    assert res["results"][0]["explanation"] == "See [1] and ."
    assert len(res["results"][0]["citations"]) == 1
