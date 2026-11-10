"""Pydantic request/response schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- auth / settings
class RegisterIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=200)
    display_name: str = Field(default="Student", max_length=120)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or v.startswith("@") or v.endswith("@"):
            raise ValueError("Enter a valid email address")
        return v


class LoginIn(BaseModel):
    email: str
    password: str


class UserOut(ORM):
    id: str
    email: str
    display_name: str
    is_local_default: bool


class SettingsOut(ORM):
    ai_mode: Literal["auto", "local_only", "cloud_only"]
    default_teaching_level: int
    cloud_consent: bool
    cloud_consent_at: datetime | None
    voice_rate: float
    voice_name: str | None
    daily_review_goal: int
    display_name: str | None = None


class SettingsIn(BaseModel):
    ai_mode: Literal["auto", "local_only", "cloud_only"] | None = None
    default_teaching_level: int | None = Field(default=None, ge=1, le=5)
    cloud_consent: bool | None = None
    voice_rate: float | None = Field(default=None, ge=0.5, le=2.0)
    voice_name: str | None = None
    daily_review_goal: int | None = Field(default=None, ge=1, le=500)
    display_name: str | None = Field(default=None, min_length=1, max_length=120)


# ---------------------------------------------------------------- subjects
class SubjectIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=1000)
    color: str = Field(default="#22d3ee", pattern=r"^#[0-9a-fA-F]{6}$")


class SubjectOut(ORM):
    id: int
    name: str
    slug: str
    description: str
    color: str
    is_custom: bool
    document_count: int = 0
    topic_count: int = 0


class TopicIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    subject_id: int | None = None
    parent_id: int | None = None


class TopicPatch(BaseModel):
    status: Literal["not_studied", "learning", "needs_revision", "understood", "mastered"] | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)


class TopicOut(ORM):
    id: int
    name: str
    subject_id: int | None
    parent_id: int | None
    status: str
    status_manual: bool
    questions_answered: int
    questions_correct: int
    last_studied_at: datetime | None


# ---------------------------------------------------------------- documents
class DocumentOut(ORM):
    id: str
    title: str
    original_filename: str
    file_type: str
    mime_type: str
    size_bytes: int
    status: str
    progress: int
    stage_message: str
    error_message: str | None
    warnings: list[str]
    page_count: int
    chunk_count: int
    image_count: int
    subject_id: int | None
    subject_suggested: bool
    topic_id: int | None
    has_preview: bool = False
    created_at: datetime
    updated_at: datetime
    processed_at: datetime | None
    last_opened_at: datetime | None
    last_page_viewed: int


class DocumentDetail(DocumentOut):
    outline: list[dict[str, Any]]
    page_kind: str


class DocumentPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    subject_id: int | None = None
    topic_id: int | None = None
    clear_subject: bool = False


class PageSummary(ORM):
    page_number: int
    kind: str
    title: str | None
    status: str
    is_scanned: bool
    ocr_used: bool
    image_count: int = 0
    table_count: int = 0
    char_count: int = 0
    has_notes: bool = False


class ImageOut(ORM):
    id: int
    page_number: int
    index_on_page: int
    width: int
    height: int
    ocr_text: str
    ai_description: str | None
    ai_provider: str | None
    ai_model: str | None
    origin: str
    url: str = ""


class PageDetail(ORM):
    page_number: int
    kind: str
    title: str | None
    text: str
    notes: str
    tables: list[dict[str, Any]]
    headings: list[str]
    is_scanned: bool
    ocr_used: bool
    ocr_confidence: float | None
    status: str
    error: str | None
    warnings: list[str]
    width: float | None
    height: float | None
    images: list[ImageOut] = []
    renderable: bool = False


class ViewedIn(BaseModel):
    page_number: int = Field(ge=1)


# ---------------------------------------------------------------- tutor
class ChatIn(BaseModel):
    message: str = Field(default="", max_length=8000)
    conversation_id: str | None = None
    teaching_level: int | None = Field(default=None, ge=1, le=5)
    action: str | None = None
    document_ids: list[str] = Field(default_factory=list, max_length=50)
    subject_id: int | None = None
    page_number: int | None = Field(default=None, ge=1)


class ExplainIn(BaseModel):
    document_id: str
    page_number: int = Field(ge=1)
    action: str = "in_depth"
    teaching_level: int | None = Field(default=None, ge=1, le=5)
    conversation_id: str | None = None
    message: str = ""


class DiagramIn(BaseModel):
    image_id: int
    teaching_level: int | None = Field(default=None, ge=1, le=5)
    question: str | None = Field(default=None, max_length=2000)


class CitationOut(ORM):
    label: int
    document_id: str | None
    chunk_id: str | None
    document_title: str
    page_number: int
    page_kind: str
    section: str | None
    snippet: str
    score: float
    used_in_answer: bool


class MessageOut(ORM):
    id: str
    role: str
    content: str
    action: str | None
    teaching_level: int | None
    provider: str | None
    model: str | None
    grounding: str | None
    status: str
    meta: dict[str, Any]
    created_at: datetime
    citations: list[CitationOut] = []


class ConversationOut(ORM):
    id: str
    title: str
    document_id: str | None
    subject_id: int | None
    teaching_level: int
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]


# ---------------------------------------------------------------- quizzes
QType = Literal["sba", "multi", "true_false", "fill_blank", "short", "long", "viva", "diagram"]


class QuizGenerateIn(BaseModel):
    document_ids: list[str] = Field(default_factory=list, max_length=50)
    subject_id: int | None = None
    topic: str | None = Field(default=None, max_length=200)
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    num_questions: int = Field(default=10, ge=1, le=30)
    question_types: list[QType] = Field(default_factory=lambda: ["sba"])
    title: str | None = Field(default=None, max_length=300)


class QuestionPublic(ORM):
    index: int
    type: str
    prompt: str
    options: list[str]
    topic: str | None
    difficulty: str
    image_id: int | None
    image_url: str | None = None


class QuizOut(ORM):
    id: str
    title: str
    subject_id: int | None
    topic: str | None
    difficulty: str
    question_types: list[str]
    document_ids: list[str]
    provider: str | None
    model: str | None
    warnings: list[str]
    created_at: datetime
    question_count: int = 0
    best_percent: float | None = None
    attempt_count: int = 0


class QuizDetail(QuizOut):
    questions: list[QuestionPublic]


class SubmitIn(BaseModel):
    answers: dict[str, Any]
    duration_seconds: int | None = Field(default=None, ge=0)


class AttemptOut(ORM):
    id: str
    quiz_id: str
    submitted_at: datetime
    score: float
    max_score: float
    percent: float = 0
    results: list[dict[str, Any]]
    topic_breakdown: list[dict[str, Any]]
    duration_seconds: int | None
    weak_topics: list[str] = []
    recommendations: list[str] = []


# ---------------------------------------------------------------- revision
class FlashcardGenerateIn(BaseModel):
    document_ids: list[str] = Field(default_factory=list, max_length=50)
    subject_id: int | None = None
    topic: str | None = Field(default=None, max_length=200)
    count: int = Field(default=10, ge=1, le=50)


class FlashcardIn(BaseModel):
    front: str = Field(min_length=1, max_length=4000)
    back: str = Field(min_length=1, max_length=8000)
    topic: str | None = Field(default=None, max_length=200)
    subject_id: int | None = None
    document_id: str | None = None


class FlashcardPatch(BaseModel):
    front: str | None = Field(default=None, min_length=1, max_length=4000)
    back: str | None = Field(default=None, min_length=1, max_length=8000)
    topic: str | None = None
    suspended: bool | None = None


class FlashcardOut(ORM):
    id: int
    front: str
    back: str
    topic: str | None
    subject_id: int | None
    document_id: str | None
    citation: dict[str, Any] | None
    origin: str
    provider: str | None
    ease: float
    interval_days: float
    repetitions: int
    lapses: int
    due_at: datetime
    last_reviewed_at: datetime | None
    suspended: bool
    created_at: datetime


class ReviewIn(BaseModel):
    rating: int = Field(ge=0, le=3)
