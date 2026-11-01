"""Discussions and departures logs, append-only (spec 2, 3H, 4; Pass 2 Stage A).

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-31

Additive: two new tables with the fields spec 4 names plus who recorded each row and when,
their indexes, append-only triggers and SELECT/INSERT-only grants. Nothing existing is
touched.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GRANTS = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'oak_binder_app') THEN
        GRANT SELECT, INSERT ON discussion TO oak_binder_app;
        GRANT SELECT, INSERT ON departure TO oak_binder_app;
    END IF;
END
$$
"""


def _append_only(table: str) -> None:
    op.execute(
        f"CREATE TRIGGER trg_{table}_append_only BEFORE UPDATE OR DELETE ON {table} "
        "FOR EACH ROW EXECUTE FUNCTION oak_binder_append_only()"
    )
    op.execute(
        f"CREATE TRIGGER trg_{table}_no_truncate BEFORE TRUNCATE ON {table} "
        "FOR EACH STATEMENT EXECUTE FUNCTION oak_binder_append_only()"
    )


def upgrade() -> None:
    op.create_table(
        "discussion",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("binder_id", sa.Uuid(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("participants", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("matter", sa.Text(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=True),
        sa.Column("recorded_by", sa.Text(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_discussion"),
        sa.ForeignKeyConstraint(
            ["binder_id"], ["binder.id"], name="fk_discussion_binder", ondelete="RESTRICT"
        ),
        sa.CheckConstraint("cardinality(participants) >= 1", name="ck_discussion_has_participants"),
        sa.CheckConstraint("btrim(matter) <> ''", name="ck_discussion_matter_not_blank"),
        sa.CheckConstraint("btrim(recorded_by) <> ''", name="ck_discussion_recorded_by_not_blank"),
    )
    op.create_index("ix_discussion_binder_id", "discussion", ["binder_id"])
    _append_only("discussion")

    op.create_table(
        "departure",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("binder_id", sa.Uuid(), nullable=False),
        sa.Column("requirement", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("alternative_procedure", sa.Text(), nullable=False),
        sa.Column("approved_by", sa.Text(), nullable=True),
        sa.Column("recorded_by", sa.Text(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_departure"),
        sa.ForeignKeyConstraint(
            ["binder_id"], ["binder.id"], name="fk_departure_binder", ondelete="RESTRICT"
        ),
        sa.CheckConstraint("btrim(requirement) <> ''", name="ck_departure_requirement_not_blank"),
        sa.CheckConstraint("btrim(reason) <> ''", name="ck_departure_reason_not_blank"),
        sa.CheckConstraint(
            "btrim(alternative_procedure) <> ''", name="ck_departure_alternative_not_blank"
        ),
        sa.CheckConstraint("btrim(recorded_by) <> ''", name="ck_departure_recorded_by_not_blank"),
    )
    op.create_index("ix_departure_binder_id", "departure", ["binder_id"])
    _append_only("departure")
    op.execute(GRANTS)


def downgrade() -> None:
    op.drop_index("ix_departure_binder_id", table_name="departure")
    op.drop_table("departure")
    op.drop_index("ix_discussion_binder_id", table_name="discussion")
    op.drop_table("discussion")
