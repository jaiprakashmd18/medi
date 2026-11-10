# REST API

Base URL: `http://localhost:8000`. Interactive OpenAPI docs: `/docs` (Swagger) and `/redoc`.

* Auth: in `single_user` mode no credentials are needed. In `multi_user` mode send `Authorization: Bearer <token>`
  from `/api/auth/login` (resource URLs used in `<img>` tags may pass `?access_token=`).
* Errors: `{"error": {"code": "...", "message": "...", "details": {...}}}` with appropriate HTTP status
  (404 not found, 409 conflict, 413 too large, 422 validation, 502 provider error, 503 no AI provider / consent required).
* `POST /api/tutor/chat/stream` returns Server-Sent Events: `meta` (provider, model, numbered sources), `delta`
  (text), then `done` (message id, grounding, used/invalid citations, served model) or `error`.

| Area | Method | Path | Notes |
|---|---|---|---|
| auth | GET | `/api/auth/config` |  |
| auth | POST | `/api/auth/login` |  |
| auth | GET | `/api/auth/me` |  |
| auth | POST | `/api/auth/register` |  |
| documents | GET | `/api/documents` |  |
| documents | POST | `/api/documents/upload` |  |
| documents | GET | `/api/documents/{document_id}` |  |
| documents | PATCH | `/api/documents/{document_id}` |  |
| documents | DELETE | `/api/documents/{document_id}` |  |
| documents | GET | `/api/documents/{document_id}/file` |  |
| documents | GET | `/api/documents/{document_id}/images` |  |
| documents | GET | `/api/documents/{document_id}/images/{image_id}/file` |  |
| documents | GET | `/api/documents/{document_id}/pages` |  |
| documents | GET | `/api/documents/{document_id}/pages/{page_number}` |  |
| documents | GET | `/api/documents/{document_id}/pages/{page_number}/image` |  |
| documents | POST | `/api/documents/{document_id}/reprocess` |  |
| documents | GET | `/api/documents/{document_id}/status` |  |
| documents | POST | `/api/documents/{document_id}/viewed` |  |
| exams | GET | `/api/quizzes` |  |
| exams | POST | `/api/quizzes/generate` |  |
| exams | GET | `/api/quizzes/{quiz_id}` |  |
| exams | DELETE | `/api/quizzes/{quiz_id}` |  |
| exams | GET | `/api/quizzes/{quiz_id}/results` |  |
| exams | POST | `/api/quizzes/{quiz_id}/submit` |  |
| privacy | DELETE | `/api/account/data` | Securely delete all documents (files, vectors) and learning data for the current user. |
| privacy | GET | `/api/export` | Export all of the user's learning data as JSON inside a ZIP (original files not included). |
| progress | GET | `/api/dashboard` |  |
| progress | GET | `/api/progress` |  |
| revision | GET | `/api/revision` |  |
| revision | GET | `/api/revision/cards` |  |
| revision | POST | `/api/revision/cards` |  |
| revision | PATCH | `/api/revision/cards/{card_id}` |  |
| revision | DELETE | `/api/revision/cards/{card_id}` |  |
| revision | POST | `/api/revision/cards/{card_id}/review` |  |
| revision | POST | `/api/revision/generate` |  |
| search | GET | `/api/search` |  |
| settings | GET | `/api/settings` |  |
| settings | PUT | `/api/settings` |  |
| subjects | GET | `/api/subjects` |  |
| subjects | POST | `/api/subjects` |  |
| subjects | DELETE | `/api/subjects/{subject_id}` |  |
| subjects | GET | `/api/topics` |  |
| subjects | POST | `/api/topics` |  |
| subjects | PATCH | `/api/topics/{topic_id}` |  |
| subjects | DELETE | `/api/topics/{topic_id}` |  |
| system | GET | `/api/ai/providers` |  |
| system | GET | `/api/health` |  |
| tutor | POST | `/api/tutor/chat` |  |
| tutor | POST | `/api/tutor/chat/stream` |  |
| tutor | GET | `/api/tutor/conversations/{conversation_id}` |  |
| tutor | DELETE | `/api/tutor/conversations/{conversation_id}` |  |
| tutor | POST | `/api/tutor/diagram` |  |
| tutor | POST | `/api/tutor/explain` |  |
| tutor | GET | `/api/tutor/history` |  |
| visual | GET | `/api/images` |  |
| visual | GET | `/api/images/{image_id}/labels` | Locate text labels on an ORIGINAL diagram with OCR so they can be masked for a label quiz. |
