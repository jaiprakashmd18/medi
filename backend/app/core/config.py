"""Application configuration.

All settings are read from environment variables (or a ``.env`` file in the
repository root / backend directory). Secrets such as ``ANTHROPIC_API_KEY`` are
only ever read here, on the backend, and are never sent to the frontend.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent

AIMode = Literal["auto", "local_only", "cloud_only"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(REPO_ROOT / ".env"), str(BACKEND_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "MEDI-GENIUS"
    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"

    # Storage / database
    data_dir: Path = Field(default=REPO_ROOT / "data")
    database_url: str | None = None  # defaults to sqlite in data_dir
    max_upload_mb: int = 100
    max_files_per_upload: int = 20

    # HTTP
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Auth: single_user = local desktop use, a default local profile is used.
    # multi_user = accounts with password login and bearer tokens.
    auth_mode: Literal["single_user", "multi_user"] = "single_user"
    secret_key: str = "change-me-in-production"
    token_ttl_hours: int = 24 * 7

    # AI
    ai_mode: AIMode = "auto"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-5-5"
    anthropic_fast_model: str = "claude-haiku-5-5"
    anthropic_effort: Literal["low", "medium", "high", "xhigh", "max"] = "high"
    anthropic_enable_fallbacks: bool = True
    anthropic_timeout_seconds: float = 300.0

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_vision_model: str = "llava:7b"
    ollama_timeout_seconds: float = 300.0

    # NVIDIA Nemotron reranking (optional second-stage reranker, cloud; consent-gated)
    nvidia_api_key: str | None = None
    nvidia_rerank_enabled: bool = True
    nvidia_rerank_model: str = "nvidia/nemotron-3.5-rerank-8b"
    nvidia_rerank_url: str = "https://ai.api.nvidia.com/v1/retrieval/nvidia/nemotron-3.5-rerank-8b/reranking"
    nvidia_rerank_timeout_seconds: float = 8.0
    nvidia_rerank_max_candidates: int = 24
    nvidia_rerank_max_passage_chars: int = 2000
    nvidia_rerank_max_query_chars: int = 1000

    # Tools
    tesseract_cmd: str | None = None
    tesseract_lang: str = "eng"
    soffice_path: str | None = None

    # Processing
    processing_workers: int = 2
    ocr_min_text_chars: int = 40
    chunk_size_chars: int = 1100
    chunk_overlap_chars: int = 180
    min_image_px: int = 64

    # Retrieval
    retrieval_top_k: int = 8
    retrieval_min_score: float = 0.30

    @field_validator("data_dir", mode="before")
    @classmethod
    def _resolve_data_dir(cls, v: object) -> Path:
        p = Path(str(v)).expanduser()
        if not p.is_absolute():
            p = (REPO_ROOT / p).resolve()
        return p

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{(self.data_dir / 'medigenius.db').as_posix()}"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def derived_dir(self) -> Path:
        return self.data_dir / "derived"

    @property
    def vectors_dir(self) -> Path:
        return self.data_dir / "vectors"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def anthropic_configured(self) -> bool:
        return bool(self.anthropic_api_key and self.anthropic_api_key.strip())

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.uploads_dir, self.derived_dir, self.vectors_dir, self.exports_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s
