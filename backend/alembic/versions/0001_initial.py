"""Baseline schema for PocketScore AI V1.0-A.

Creates every table declared on ``Base.metadata``.  Later revisions should be
generated with ``alembic revision --autogenerate -m "<change>"`` so schema drift
stays reviewable; this baseline exists so a fresh database can be built from
migrations alone instead of relying on ``create_all``.

Revision ID: 0001_initial
Revises:
"""

from __future__ import annotations

from alembic import op

from app.core.db import Base
from app import models  # noqa: F401  (registers all tables)

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
