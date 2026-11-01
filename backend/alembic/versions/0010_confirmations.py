"""Reference confirmation and run verification (spec 3C, 3E; Pass 2 completion work, D36 and D37).

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-01

Additive only; migrations 0001–0009 are unchanged.

- ``xref.confirmed_by``, ``confirmed_at``, ``confirmed_version`` (all nullable, all set
  together): spec 3E says a reference to a superseded paper blocks assembly. A paper target
  amended after the reference was made is such a reference until a person confirms it against
  the target's current version; the confirmation records who, when and which version. The
  ``xref`` table already grants UPDATE to the application role (0005).
- ``wp_generation.run_verification`` (nullable JSONB): how a delivery's run was verified at
  intake, today the WorkMind run read back from the configured WorkMind (status, who accepted
  it and when, the endpoint read). Set when the row is written; the table stays append-only.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONFIRMATION_COMPLETE_SQL = (
    "(confirmed_by IS NULL AND confirmed_at IS NULL AND confirmed_version IS NULL) OR "
    "(confirmed_by IS NOT NULL AND btrim(confirmed_by) <> '' AND confirmed_at IS NOT NULL "
    "AND confirmed_version IS NOT NULL AND confirmed_version >= 1)"
)


def upgrade() -> None:
    op.add_column("xref", sa.Column("confirmed_by", sa.Text(), nullable=True))
    op.add_column("xref", sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("xref", sa.Column("confirmed_version", sa.Integer(), nullable=True))
    op.create_check_constraint("ck_xref_confirmation_complete", "xref", CONFIRMATION_COMPLETE_SQL)
    op.add_column(
        "wp_generation",
        sa.Column("run_verification", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("wp_generation", "run_verification")
    op.drop_constraint("ck_xref_confirmation_complete", "xref", type_="check")
    op.drop_column("xref", "confirmed_version")
    op.drop_column("xref", "confirmed_at")
    op.drop_column("xref", "confirmed_by")
