"""SQLAlchemy ORM models for MEDI-GENIUS.

Hierarchy: Subject -> Topic -> Document -> DocumentPage -> Chunk/DocumentImage.
Deleting a document cascades to all derived rows (pages, images, chunks,
citations); vectors and derived files are removed by the document service.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return uuid.uuid4().hex


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


# --------------------------------------------------------------------------- users
class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120), default="Student")
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_local_default: Mapped[bool] = mapped_column(Boolean, default=False)

    settings: Mapped[UserSettings | None] = relationship(back_populates="user", uselist=False,
                                                        cascade="all, delete-orphan")


class UserSettings(TimestampMixin, Base):
    __tablename__ = "user_settings"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    ai_mode: Mapped[str] = mapped_column(String(20), default="auto")
    default_teaching_level: Mapped[int] = mapped_column(Integer, default=2)
    cloud_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    cloud_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Separate, revocable consent for sending retrieved passages to NVIDIA for reranking
    nvidia_consent: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    nvidia_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voice_rate: Mapped[float] = mapped_column(Float, default=1.0)
    voice_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    daily_review_goal: Mapped[int] = mapped_column(Integer, default=20)
    preferences: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    user: Mapped[User] = relationship(back_populates="settings")


# --------------------------------------------------------------------------- library
class Subject(TimestampMixin, Base):
    __tablename__ = "subjects"
    __table_args__ = (UniqueConstraint("user_id", "slug", name="uq_subject_user_slug"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # NULL user_id = built-in subject shared by all users
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(120), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    color: Mapped[str] = mapped_column(String(20), default="#22d3ee")
    is_custom: Mapped[bool] = mapped_column(Boolean, default=False)


class Topic(TimestampMixin, Base):
    """A topic/subtopic a user studies. Also holds the user's learning status."""
    __tablename__ = "topics"
    __table_args__ = (UniqueConstraint("user_id", "subject_id", "parent_id", "name", name="uq_topic_scope_name"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    subject_id: Mapped[int | None] = mapped_column(ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"), nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    # not_studied | learning | needs_revision | understood | mastered
    status: Mapped[str] = mapped_column(String(20), default="not_studied")
    status_manual: Mapped[bool] = mapped_column(Boolean, default=False)
    questions_answered: Mapped[int] = mapped_column(Integer, default=0)
    questions_correct: Mapped[int] = mapped_column(Integer, default=0)
    tutor_messages: Mapped[int] = mapped_column(Integer, default=0)
    last_studied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Document(TimestampMixin, Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    subject_id: Mapped[int | None] = mapped_column(ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True)
    subject_suggested: Mapped[bool] = mapped_column(Boolean, default=False)
    topic_id: Mapped[int | None] = mapped_column(ForeignKey("topics.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(300))
    original_filename: Mapped[str] = mapped_column(String(300))
    stored_path: Mapped[str] = mapped_column(String(500))  # relative to data_dir
    file_type: Mapped[str] = mapped_column(String(10))  # pdf | pptx | docx | image
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    # uploaded|validating|stored|extracting|ocr|analysing_images|chunking|embedding|indexing|ready|partial|failed
    status: Mapped[str] = mapped_column(String(20), default="uploaded", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    stage_message: Mapped[str] = mapped_column(String(300), default="")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    image_count: Mapped[int] = mapped_column(Integer, default=0)
    outline: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    preview_pdf_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    processing_attempts: Mapped[int] = mapped_column(Integer, default=0)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_page_viewed: Mapped[int] = mapped_column(Integer, default=1)

    pages: Mapped[list[DocumentPage]] = relationship(back_populates="document", cascade="all, delete-orphan",
                                                     order_by="DocumentPage.page_number", passive_deletes=True)
    images: Mapped[list[DocumentImage]] = relationship(back_populates="document", cascade="all, delete-orphan",
                                                       passive_deletes=True)
    chunks: Mapped[list[Chunk]] = relationship(back_populates="document", cascade="all, delete-orphan",
                                               passive_deletes=True)


class DocumentPage(Base):
    __tablename__ = "document_pages"
    __table_args__ = (UniqueConstraint("document_id", "page_number", name="uq_page_doc_number"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    page_number: Mapped[int] = mapped_column(Integer)  # 1-based page / slide / section index
    kind: Mapped[str] = mapped_column(String(10), default="page")  # page | slide | section | image
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    text: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")  # PPTX speaker notes
    tables: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    headings: Mapped[list[str]] = mapped_column(JSON, default=list)
    is_scanned: Mapped[bool] = mapped_column(Boolean, default=False)
    ocr_used: Mapped[bool] = mapped_column(Boolean, default=False)
    ocr_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(10), default="ok")  # ok | partial | failed
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    width: Mapped[float | None] = mapped_column(Float, nullable=True)
    height: Mapped[float | None] = mapped_column(Float, nullable=True)

    document: Mapped[Document] = relationship(back_populates="pages")


class DocumentImage(Base):
    __tablename__ = "document_images"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    page_number: Mapped[int] = mapped_column(Integer)
    index_on_page: Mapped[int] = mapped_column(Integer, default=0)
    path: Mapped[str] = mapped_column(String(500))  # relative to data_dir
    mime_type: Mapped[str] = mapped_column(String(50), default="image/png")
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    ocr_text: Mapped[str] = mapped_column(Text, default="")
    ai_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ai_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Always "original" for extracted images: AI never generates source diagrams.
    origin: Mapped[str] = mapped_column(String(20), default="original")

    document: Mapped[Document] = relationship(back_populates="images")


class Chunk(Base):
    __tablename__ = "chunks"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    page_number: Mapped[int] = mapped_column(Integer)
    chunk_index: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(20), default="text")  # text | table | notes | image_text
    section: Mapped[str | None] = mapped_column(String(500), nullable=True)
    text: Mapped[str] = mapped_column(Text)
    image_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    suspicious: Mapped[bool] = mapped_column(Boolean, default=False)  # possible prompt injection
    indexed: Mapped[bool] = mapped_column(Boolean, default=False)

    document: Mapped[Document] = relationship(back_populates="chunks")


# --------------------------------------------------------------------------- tutor
class Conversation(TimestampMixin, Base):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    subject_id: Mapped[int | None] = mapped_column(ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(300), default="New conversation")
    teaching_level: Mapped[int] = mapped_column(Integer, default=2)

    messages: Mapped[list[Message]] = relationship(back_populates="conversation", cascade="all, delete-orphan",
                                                   order_by="Message.created_at", passive_deletes=True)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(10))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    action: Mapped[str | None] = mapped_column(String(30), nullable=True)
    teaching_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider: Mapped[str | None] = mapped_column(String(30), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # documents = grounded in retrieved sources; general = no sources used; insufficient = sources weak
    grounding: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(15), default="complete")  # complete | error | partial
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
    citations: Mapped[list[Citation]] = relationship(back_populates="message", cascade="all, delete-orphan",
                                                     order_by="Citation.label", passive_deletes=True)


class Citation(Base):
    __tablename__ = "citations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[str] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), index=True)
    label: Mapped[int] = mapped_column(Integer)  # the [n] marker used in the answer
    document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    chunk_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    document_title: Mapped[str] = mapped_column(String(300))
    page_number: Mapped[int] = mapped_column(Integer)
    page_kind: Mapped[str] = mapped_column(String(10), default="page")
    section: Mapped[str | None] = mapped_column(String(500), nullable=True)
    snippet: Mapped[str] = mapped_column(Text, default="")
    score: Mapped[float] = mapped_column(Float, default=0.0)
    used_in_answer: Mapped[bool] = mapped_column(Boolean, default=False)

    message: Mapped[Message] = relationship(back_populates="citations")


# --------------------------------------------------------------------------- exams
class Quiz(TimestampMixin, Base):
    __tablename__ = "quizzes"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    subject_id: Mapped[int | None] = mapped_column(ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True)
    topic: Mapped[str | None] = mapped_column(String(200), nullable=True)
    difficulty: Mapped[str] = mapped_column(String(20), default="medium")
    question_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    document_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    provider: Mapped[str | None] = mapped_column(String(30), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)

    questions: Mapped[list[Question]] = relationship(back_populates="quiz", cascade="all, delete-orphan",
                                                     order_by="Question.index", passive_deletes=True)
    attempts: Mapped[list[Attempt]] = relationship(back_populates="quiz", cascade="all, delete-orphan",
                                                   passive_deletes=True)


class Question(Base):
    __tablename__ = "questions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    quiz_id: Mapped[str] = mapped_column(ForeignKey("quizzes.id", ondelete="CASCADE"), index=True)
    index: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(20))  # sba|multi|true_false|fill_blank|short|long|viva|diagram
    prompt: Mapped[str] = mapped_column(Text)
    options: Mapped[list[str]] = mapped_column(JSON, default=list)
    correct_answer: Mapped[Any] = mapped_column(JSON)  # index list for MCQ, bool, string(s)
    model_answer: Mapped[str] = mapped_column(Text, default="")
    key_points: Mapped[list[str]] = mapped_column(JSON, default=list)
    explanation: Mapped[str] = mapped_column(Text, default="")
    topic: Mapped[str | None] = mapped_column(String(200), nullable=True)
    difficulty: Mapped[str] = mapped_column(String(20), default="medium")
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    image_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    quiz: Mapped[Quiz] = relationship(back_populates="questions")


class Attempt(Base):
    __tablename__ = "attempts"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    quiz_id: Mapped[str] = mapped_column(ForeignKey("quizzes.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    score: Mapped[float] = mapped_column(Float, default=0)
    max_score: Mapped[float] = mapped_column(Float, default=0)
    answers: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    results: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    topic_breakdown: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    quiz: Mapped[Quiz] = relationship(back_populates="attempts")


# --------------------------------------------------------------------------- revision
class Flashcard(TimestampMixin, Base):
    __tablename__ = "flashcards"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    subject_id: Mapped[int | None] = mapped_column(ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True)
    topic: Mapped[str | None] = mapped_column(String(200), nullable=True)
    front: Mapped[str] = mapped_column(Text)
    back: Mapped[str] = mapped_column(Text)
    citation: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    origin: Mapped[str] = mapped_column(String(20), default="ai")  # ai | manual | quiz_mistake
    provider: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # SM-2 scheduling state
    ease: Mapped[float] = mapped_column(Float, default=2.5)
    interval_days: Mapped[float] = mapped_column(Float, default=0)
    repetitions: Mapped[int] = mapped_column(Integer, default=0)
    lapses: Mapped[int] = mapped_column(Integer, default=0)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    suspended: Mapped[bool] = mapped_column(Boolean, default=False)


class ReviewLog(Base):
    __tablename__ = "review_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    flashcard_id: Mapped[int] = mapped_column(ForeignKey("flashcards.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    rating: Mapped[int] = mapped_column(Integer)  # 0 again, 1 hard, 2 good, 3 easy
    interval_days: Mapped[float] = mapped_column(Float)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class StudySession(Base):
    __tablename__ = "study_sessions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # reading | tutor | quiz | revision
    document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    conversation_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    quiz_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    title: Mapped[str] = mapped_column(String(300), default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    activity_count: Mapped[int] = mapped_column(Integer, default=1)
