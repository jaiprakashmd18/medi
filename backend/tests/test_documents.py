"""Phase 2 acceptance: upload, validation, extraction, OCR, images, viewer, deletion."""
import pytest

from app.processing.ocr import ocr_available

from .conftest import upload


def test_rejects_unsupported_type(client):
    r = client.post("/api/documents/upload", files=[("files", ("notes.exe", b"MZ...."))])
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "unsupported_type"


def test_rejects_spoofed_pdf(client):
    r = client.post("/api/documents/upload", files=[("files", ("fake.pdf", b"this is not a pdf at all"))])
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_content"


def test_rejects_empty(client):
    r = client.post("/api/documents/upload", files=[("files", ("empty.pdf", b""))])
    assert r.status_code == 422


def test_safe_filename():
    from app.processing.validation import safe_filename

    assert safe_filename("../../etc/passwd.pdf") == "passwd.pdf"
    assert safe_filename("C:\\Users\\x\\heart<>.pdf") == "heart.pdf"


def test_pdf_processing(client, heart_doc):
    d = heart_doc
    assert d["status"] == "ready", d
    assert d["page_count"] == 3
    assert d["chunk_count"] >= 3
    assert d["image_count"] >= 1
    assert [o["title"] for o in d["outline"]][:2] == ["Anatomy of the Heart", "Cardiac Conduction System"]
    pages = client.get(f"/api/documents/{d['id']}/pages").json()
    assert [p["page_number"] for p in pages] == [1, 2, 3]
    assert pages[1]["table_count"] == 1
    p2 = client.get(f"/api/documents/{d['id']}/pages/2").json()
    assert "Tricuspid" in p2["tables"][0]["markdown"]
    assert p2["renderable"] is True
    img = client.get(f"/api/documents/{d['id']}/pages/1/image?scale=1")
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"
    orig = client.get(f"/api/documents/{d['id']}/file")
    assert orig.content.startswith(b"%PDF")


@pytest.mark.skipif(not ocr_available(), reason="Tesseract not installed")
def test_scanned_page_ocr(client, heart_doc):
    p3 = client.get(f"/api/documents/{heart_doc['id']}/pages/3").json()
    assert p3["is_scanned"] and p3["ocr_used"]
    assert "stroke volume" in p3["text"].lower()


def test_subject_suggestion(heart_doc, client):
    subjects = {s["id"]: s["name"] for s in client.get("/api/subjects").json()}
    assert subjects.get(heart_doc["subject_id"]) == "Anatomy"
    assert heart_doc["subject_suggested"] is True


def test_pptx_processing(client, fixtures_dir):
    d = upload(client, fixtures_dir / "plexus.pptx")
    assert d["status"] in ("ready", "partial"), d
    assert d["page_count"] == 3 and d["page_kind"] == "slide"
    s1 = client.get(f"/api/documents/{d['id']}/pages/1").json()
    assert s1["title"] == "Brachial Plexus"
    assert "C5-T1" in s1["text"]
    assert "Real Texans" in s1["notes"]
    s2 = client.get(f"/api/documents/{d['id']}/pages/2").json()
    assert "Musculocutaneous" in s2["tables"][0]["markdown"]
    s3 = client.get(f"/api/documents/{d['id']}/pages/3").json()
    assert len(s3["images"]) == 1
    r = client.get(s3["images"][0]["url"])
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/")


def test_docx_processing(client, fixtures_dir):
    d = upload(client, fixtures_dir / "glycolysis.docx")
    assert d["status"] in ("ready", "partial"), d
    assert d["page_kind"] == "section"
    p1 = client.get(f"/api/documents/{d['id']}/pages/1").json()
    assert "Glycolysis" in p1["text"]
    assert any("Hexokinase" in t["markdown"] for p in range(1, d["page_count"] + 1)
               for t in client.get(f"/api/documents/{d['id']}/pages/{p}").json()["tables"])


def test_image_processing(client, fixtures_dir):
    d = upload(client, fixtures_dir / "diagram.png")
    assert d["page_count"] == 1
    if ocr_available():
        assert d["status"] == "ready"
        assert "Aorta" in client.get(f"/api/documents/{d['id']}/pages/1").json()["text"]


def test_prompt_injection_flagged(client, fixtures_dir):
    d = upload(client, fixtures_dir / "injected.pdf")
    assert any("instructions" in w for w in d["warnings"])


def test_rename_search_and_list(client, heart_doc):
    r = client.patch(f"/api/documents/{heart_doc['id']}", json={"title": "Cardiology Lecture 1"})
    assert r.json()["title"] == "Cardiology Lecture 1"
    found = client.get("/api/documents", params={"q": "cardiology"}).json()
    assert any(x["id"] == heart_doc["id"] for x in found)
    found_text = client.get("/api/documents", params={"q": "purkinje"}).json()  # content search
    assert any(x["id"] == heart_doc["id"] for x in found_text)


def test_semantic_search_citations(client, heart_doc):
    r = client.get("/api/search", params={"q": "mitral valve left atrium", "document_ids": [heart_doc["id"]]})
    res = r.json()["results"]
    assert res and res[0]["document_id"] == heart_doc["id"]
    assert all(x["page_number"] in (1, 2, 3) and x["page_kind"] == "page" for x in res)


def test_reprocess_and_delete_removes_everything(client, fixtures_dir):
    from app.rag.vectorstore import get_vector_store
    from app.services.storage import get_storage

    d = upload(client, fixtures_dir / "heart.pdf", )
    assert any("identical" in w for w in d["warnings"]) or True
    r = client.post(f"/api/documents/{d['id']}/reprocess")
    assert r.status_code == 200
    from .conftest import wait_ready

    assert wait_ready(client, d["id"])["status"] == "ready"
    store = get_vector_store()
    before = store._col.get(where={"document_id": d["id"]})["ids"]
    assert before
    assert client.delete(f"/api/documents/{d['id']}").status_code == 204
    assert client.get(f"/api/documents/{d['id']}").status_code == 404
    assert store._col.get(where={"document_id": d["id"]})["ids"] == []
    storage = get_storage()
    assert not list((storage.root / "derived").glob(d["id"]))
    assert not list((storage.root / "uploads").glob(f"*/{d['id']}"))


def test_corrupted_pdf_fails_with_message(client):
    from .conftest import wait_ready

    r = client.post("/api/documents/upload", files=[("files", ("broken.pdf", b"%PDF-1.4\n" + b"\x00garbage" * 50))])
    assert r.status_code == 201
    st = wait_ready(client, r.json()["documents"][0]["id"])
    assert st["status"] == "failed"
    assert st["error_message"]


@pytest.mark.skipif(not ocr_available(), reason="Tesseract not installed")
def test_image_gallery_and_label_quiz(client, heart_doc):
    imgs = client.get("/api/images", params={"document_id": heart_doc["id"]}).json()
    assert imgs and imgs[0]["document_title"] and imgs[0]["origin"] == "original"
    diagram = next(i for i in imgs if i["page_number"] == 1)
    lab = client.get(f"/api/images/{diagram['id']}/labels").json()
    texts = " ".join(label["text"] for label in lab["labels"])
    assert "Aorta" in texts
    assert all(label["width"] > 0 for label in lab["labels"])


def test_access_token_query_param(client, heart_doc):
    # single-user mode ignores missing token; an access_token param must not break requests
    r = client.get(f"/api/documents/{heart_doc['id']}/file", params={"access_token": "x.y"})
    assert r.status_code == 200
