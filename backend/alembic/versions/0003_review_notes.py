"""Review notes: raised -> assigned -> responded -> cleared, append-only (spec 3D, 4, 8.2).

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-29

Additive: one new table, its triggers and grants. Nothing existing is touched. The downgrade
drops the table and is never run against data by default.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATES = "'raised', 'assigned', 'responded', 'cleared'"

GRANTS = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'oak_binder_app') THEN
        GRANT SELECT, INSERT ON review_note TO oak_binder_app;
    END IF;
END
$$
"""


def upgrade() -> None:
    op.create_table(
        "review_note",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("note_id", sa.Uuid(), nullable=False),
        sa.Column("step", sa.Integer(), nullable=False),
        sa.Column("wp_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("raised_by", sa.Text(), nullable=False),
        sa.Column("assigned_to", sa.Text(), nullable=True),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cleared_by", sa.Text(), nullable=True),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_review_note"),
        sa.ForeignKeyConstraint(
            ["wp_id"], ["wp.id"], name="fk_review_note_wp", ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("note_id", "step", name="uq_review_note_note_step"),
        sa.CheckConstraint("step >= 1", name="ck_review_note_step_positive"),
        sa.CheckConstraint(f"state IN ({STATES})", name="ck_review_note_state"),
        sa.CheckConstraint("btrim(raised_by) <> ''", name="ck_review_note_raised_by_not_blank"),
        sa.CheckConstraint("btrim(actor) <> ''", name="ck_review_note_actor_not_blank"),
        sa.CheckConstraint(
            "state <> 'raised' OR (text IS NOT NULL AND btrim(text) <> '')",
            name="ck_review_note_raised_has_text",
        ),
        sa.CheckConstraint(
            "state <> 'assigned' OR assigned_to IS NOT NULL",
            name="ck_review_note_assigned_has_assignee",
        ),
        sa.CheckConstraint(
            "(state = 'responded') = (responded_at IS NOT NULL)",
            name="ck_review_note_responded_at",
        ),
        sa.CheckConstraint(
            "(state = 'cleared') = (cleared_by IS NOT NULL)", name="ck_review_note_cleared_by"
        ),
    )
    op.create_index("ix_review_note_wp_id", "review_note", ["wp_id"])
    op.execute(
        "CREATE TRIGGER trg_review_note_append_only BEFORE UPDATE OR DELETE ON review_note "
        "FOR EACH ROW EXECUTE FUNCTION oak_binder_append_only()"
    )
    op.execute(
        "CREATE TRIGGER trg_review_note_no_truncate BEFORE TRUNCATE ON review_note "
        "FOR EACH STATEMENT EXECUTE FUNCTION oak_binder_append_only()"
    )
    op.execute(GRANTS)


def downgrade() -> None:
    op.drop_index("ix_review_note_wp_id", table_name="review_note")
    op.drop_table("review_note")
