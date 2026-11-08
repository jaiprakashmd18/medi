"""Run Alembic migrations programmatically (used at startup and by scripts)."""
from __future__ import annotations

from alembic import command
from alembic.config import Config

from app.core.config import BACKEND_DIR, get_settings


def alembic_config() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", get_settings().sqlalchemy_url)
    return cfg


def upgrade_head() -> None:
    command.upgrade(alembic_config(), "head")
