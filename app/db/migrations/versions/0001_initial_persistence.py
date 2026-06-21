"""Initial persistence schema.

Revision ID: 0001_initial_persistence
Revises:
Create Date: 2026-06-20 00:00:00
"""
from alembic import op

from app.db import models  # noqa: F401
from app.db.database import Base

revision = "0001_initial_persistence"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())

