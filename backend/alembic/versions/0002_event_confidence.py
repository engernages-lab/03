"""Add music_events.confidence (V1.1-A transcribed-note confidence).

Revision ID: 0002_event_confidence
Revises: 0001_initial
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_event_confidence"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return False
    return any(item["name"] == column for item in inspector.get_columns(table))


def upgrade() -> None:
    # create_all() already adds the column for fresh databases; this keeps
    # existing installations in sync.
    if not _has_column("music_events", "confidence"):
        op.add_column("music_events", sa.Column("confidence", sa.Float(), nullable=True))


def downgrade() -> None:
    if _has_column("music_events", "confidence"):
        with op.batch_alter_table("music_events") as batch:
            batch.drop_column("confidence")
