"""The binder's link to a Financial Spine engagement and version (spec 3A; Pass 2 Stage B).

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-31

Additive: two nullable columns on binder and one check. No foreign keys: the ids belong to
the Spine's own database. Existing rows are untouched (both columns null). The application
role's existing UPDATE on binder covers them.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("binder", sa.Column("spine_engagement_id", sa.Uuid(), nullable=True))
    op.add_column("binder", sa.Column("spine_version_id", sa.Uuid(), nullable=True))
    op.create_check_constraint(
        "ck_binder_spine_version_needs_engagement",
        "binder",
        "spine_version_id IS NULL OR spine_engagement_id IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint("ck_binder_spine_version_needs_engagement", "binder", type_="check")
    op.drop_column("binder", "spine_version_id")
    op.drop_column("binder", "spine_engagement_id")
