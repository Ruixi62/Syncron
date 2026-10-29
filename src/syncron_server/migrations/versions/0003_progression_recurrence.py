"""Progression des conditions de R&D (380 / 1 000) et événements récurrents.

- research_lines.progress : quantité déjà réunie pour une condition chiffrée.
- calendar_events : règle de récurrence (quotidienne, hebdomadaire sur des jours
  choisis, mensuelle), intervalle, date de fin, dates annulées.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("research_lines", sa.Column("progress", sa.BigInteger(), nullable=True))
    op.create_check_constraint(
        op.f("ck_research_lines_progress"), "research_lines", "progress is null or progress >= 0"
    )

    columns = (
        sa.Column("recurrence", sa.String(length=8), nullable=False, server_default="none"),
        sa.Column("recurrence_interval", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("recurrence_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recurrence_until", sa.Date(), nullable=True),
        sa.Column("skipped_dates", sa.JSON(), nullable=False, server_default="[]"),
    )
    for column in columns:
        op.add_column("calendar_events", column)
    for name in ("recurrence", "recurrence_interval", "recurrence_days", "skipped_dates"):
        op.alter_column("calendar_events", name, server_default=None)
    op.create_check_constraint(
        op.f("ck_calendar_events_recurrence"),
        "calendar_events",
        "recurrence in ('none', 'daily', 'weekly', 'monthly')",
    )
    op.create_check_constraint(
        op.f("ck_calendar_events_recurrence_interval"), "calendar_events", "recurrence_interval between 1 and 52"
    )
    op.create_check_constraint(
        op.f("ck_calendar_events_recurrence_days"), "calendar_events", "recurrence_days between 0 and 127"
    )


def downgrade() -> None:
    for name in ("recurrence_days", "recurrence_interval", "recurrence"):
        op.drop_constraint(op.f(f"ck_calendar_events_{name}"), "calendar_events", type_="check")
    for name in ("skipped_dates", "recurrence_until", "recurrence_days", "recurrence_interval", "recurrence"):
        op.drop_column("calendar_events", name)
    op.drop_constraint(op.f("ck_research_lines_progress"), "research_lines", type_="check")
    op.drop_column("research_lines", "progress")
