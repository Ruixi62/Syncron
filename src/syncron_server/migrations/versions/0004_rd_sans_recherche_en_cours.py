"""R&D sans « recherche en cours », récompenses en texte, conditions cochées seulement une fois atteintes.

- research_categories.active disparaît (avec son index unique et sa contrainte) : un palier est
  simplement validé quand il a été fait en jeu.
- Récompenses : texte seul. Les récompenses qui citaient un objet du catalogue sont réécrites
  en texte (« 64 × Lingot de fer — pour la forge »).
- Conditions chiffrées : cochées seulement si la quantité réunie atteint la quantité demandée ;
  les cases cochées trop tôt sont décochées.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        update research_lines as line
        set text = left(
                case when line.quantity is not null then line.quantity::text || ' × ' else '' end
                || case
                    when line.item_id is null then line.text
                    when line.text <> '' then coalesce(item.name, line.item_id) || ' — ' || line.text
                    else coalesce(item.name, line.item_id)
                end,
                300
            ),
            item_id = null,
            quantity = null,
            progress = null,
            done = false
        from research_lines as source
        left join items as item on item.id = source.item_id
        where line.id = source.id
          and line.kind = 'reward'
          and (line.item_id is not null or line.quantity is not null or line.progress is not null or line.done)
        """
    )
    op.execute(
        """
        update research_lines
        set done = false
        where kind = 'condition' and done and quantity is not null and coalesce(progress, 0) < quantity
        """
    )
    op.create_check_constraint(
        op.f("ck_research_lines_reward_text"),
        "research_lines",
        "kind = 'condition' or (item_id is null and quantity is null and progress is null)",
    )
    op.create_check_constraint(
        op.f("ck_research_lines_done_reached"),
        "research_lines",
        "not done or quantity is null or coalesce(progress, 0) >= quantity",
    )

    op.drop_index("uq_research_categories_active", table_name="research_categories", postgresql_where="active")
    op.drop_constraint(op.f("ck_research_categories_active"), "research_categories", type_="check")
    op.drop_column("research_categories", "active")


def downgrade() -> None:
    op.add_column("research_categories", sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.alter_column("research_categories", "active", server_default=None)
    op.create_check_constraint(
        op.f("ck_research_categories_active"), "research_categories", "not active or completed < tier_count"
    )
    op.create_index(
        "uq_research_categories_active", "research_categories", ["active"], unique=True, postgresql_where="active"
    )
    op.drop_constraint(op.f("ck_research_lines_done_reached"), "research_lines", type_="check")
    op.drop_constraint(op.f("ck_research_lines_reward_text"), "research_lines", type_="check")
