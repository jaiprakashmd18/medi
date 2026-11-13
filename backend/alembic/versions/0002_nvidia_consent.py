"""NVIDIA rerank consent on user settings

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-13
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("user_settings") as batch:
        batch.add_column(sa.Column("nvidia_consent", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("nvidia_consent_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("user_settings") as batch:
        batch.drop_column("nvidia_consent_at")
        batch.drop_column("nvidia_consent")
