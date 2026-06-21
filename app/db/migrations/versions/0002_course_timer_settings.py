"""Add course timer settings.

Revision ID: 0002_course_timer_settings
Revises: 0001_initial_persistence
Create Date: 2026-06-20 22:45:00
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_course_timer_settings"
down_revision = "0001_initial_persistence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "courses",
        sa.Column("default_mode", sa.String(), nullable=False, server_default="OPEN_GYM"),
    )
    op.add_column(
        "courses",
        sa.Column("countdown_seconds", sa.Integer(), nullable=False, server_default="3"),
    )
    op.add_column(
        "courses",
        sa.Column("false_start_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "courses",
        sa.Column("false_start_sensitivity", sa.Integer(), nullable=False, server_default="5"),
    )
    op.add_column(
        "courses",
        sa.Column("relay_start_lights", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "courses",
        sa.Column("relay_finish_chime", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "courses",
        sa.Column("relay_smoke_burst", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "courses",
        sa.Column("relay_crowd_cheer", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("courses", "relay_crowd_cheer")
    op.drop_column("courses", "relay_smoke_burst")
    op.drop_column("courses", "relay_finish_chime")
    op.drop_column("courses", "relay_start_lights")
    op.drop_column("courses", "false_start_sensitivity")
    op.drop_column("courses", "false_start_enabled")
    op.drop_column("courses", "countdown_seconds")
    op.drop_column("courses", "default_mode")
