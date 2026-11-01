"""Review levels, configurable per engagement (spec 3D; Pass 2 Stage F, D33).

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-01

Additive: one nullable column, ``binder.review_levels`` (the ordered review levels after the
preparer; NULL keeps the Pass 1 single-review behaviour), and one append-only table,
``wp_review``, one row per level review naming the prepared version reviewed, the level, the
reviewer and the time. The configuration freezes at the database once any level review exists
for a paper of the binder: a trigger refuses the update. Migrations 0001–0008 are unchanged.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FROZEN_FUNCTION = """
CREATE FUNCTION oak_binder_review_levels_frozen() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.review_levels IS DISTINCT FROM OLD.review_levels AND EXISTS (
        SELECT 1 FROM wp_review r JOIN wp ON wp.id = r.wp_id WHERE wp.binder_id = OLD.id
    ) THEN
        RAISE EXCEPTION 'binder review levels are frozen: a level review has been recorded (spec 3D, 3F; architecture D33)'
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
END
$$
"""

GRANTS = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'oak_binder_app') THEN
        GRANT SELECT, INSERT ON wp_review TO oak_binder_app;
    END IF;
END
$$
"""


def upgrade() -> None:
    op.add_column(
        "binder", sa.Column("review_levels", postgresql.ARRAY(sa.Text()), nullable=True)
    )
    op.create_check_constraint(
        "ck_binder_review_levels_not_empty",
        "binder",
        "review_levels IS NULL OR cardinality(review_levels) >= 1",
    )
    op.create_table(
        "wp_review",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("wp_id", sa.Uuid(), nullable=False),
        sa.Column("wp_version_id", sa.Uuid(), nullable=False),
        sa.Column("level", sa.Text(), nullable=False),
        sa.Column("reviewer", sa.Text(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_wp_review"),
        sa.ForeignKeyConstraint(["wp_id"], ["wp.id"], name="fk_wp_review_wp", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["wp_version_id"],
            ["wp_version.id"],
            name="fk_wp_review_wp_version",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("wp_version_id", "level", name="uq_wp_review_version_level"),
        sa.CheckConstraint("btrim(level) <> ''", name="ck_wp_review_level_not_blank"),
        sa.CheckConstraint("btrim(reviewer) <> ''", name="ck_wp_review_reviewer_not_blank"),
    )
    op.create_index("ix_wp_review_wp_id", "wp_review", ["wp_id"])
    op.execute(
        "CREATE TRIGGER trg_wp_review_append_only BEFORE UPDATE OR DELETE ON wp_review "
        "FOR EACH ROW EXECUTE FUNCTION oak_binder_append_only()"
    )
    op.execute(
        "CREATE TRIGGER trg_wp_review_no_truncate BEFORE TRUNCATE ON wp_review "
        "FOR EACH STATEMENT EXECUTE FUNCTION oak_binder_append_only()"
    )
    op.execute(FROZEN_FUNCTION)
    op.execute(
        "CREATE TRIGGER trg_binder_review_levels_frozen BEFORE UPDATE OF review_levels ON binder "
        "FOR EACH ROW EXECUTE FUNCTION oak_binder_review_levels_frozen()"
    )
    op.execute(GRANTS)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_binder_review_levels_frozen ON binder")
    op.execute("DROP FUNCTION IF EXISTS oak_binder_review_levels_frozen()")
    op.drop_index("ix_wp_review_wp_id", table_name="wp_review")
    op.drop_table("wp_review")
    op.drop_constraint("ck_binder_review_levels_not_empty", "binder", type_="check")
    op.drop_column("binder", "review_levels")
