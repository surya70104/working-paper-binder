"""Generated-paper provenance, append-only (spec 3C, 8.8; Pass 2 Stage D, D31).

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-31

Additive: one new table, ``wp_generation``, one row per paper a module delivered: the source,
the module, its run, when it generated the paper, who delivered it and when, the whole
provenance block as received, and the content hash of the module's fields at intake. Append-
only trigger and SELECT/INSERT-only grants like every record table. Nothing existing is
touched; migrations 0001–0007 are unchanged.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GRANTS = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'oak_binder_app') THEN
        GRANT SELECT, INSERT ON wp_generation TO oak_binder_app;
    END IF;
END
$$
"""

SOURCES = "'materiality', 'sampling', 'analytical_review', 'workmind', 'spine'"


def upgrade() -> None:
    op.create_table(
        "wp_generation",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("wp_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("module", sa.Text(), nullable=False),
        sa.Column("module_version", sa.Text(), nullable=True),
        sa.Column("run_id", sa.Text(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_by", sa.Text(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("content_hash_at_intake", sa.Text(), nullable=False),
        sa.Column("spine_figures", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_wp_generation"),
        sa.ForeignKeyConstraint(
            ["wp_id"], ["wp.id"], name="fk_wp_generation_wp", ondelete="RESTRICT"
        ),
        sa.CheckConstraint(f"source IN ({SOURCES})", name="ck_wp_generation_source"),
        sa.CheckConstraint("btrim(module) <> ''", name="ck_wp_generation_module_not_blank"),
        sa.CheckConstraint(
            "run_id IS NULL OR btrim(run_id) <> ''", name="ck_wp_generation_run_id_not_blank"
        ),
        sa.CheckConstraint(
            "btrim(received_by) <> ''", name="ck_wp_generation_received_by_not_blank"
        ),
        sa.CheckConstraint(
            "content_hash_at_intake ~ '^[0-9a-f]{64}$'", name="ck_wp_generation_content_hash"
        ),
        sa.CheckConstraint(
            "spine_figures IS NULL OR spine_figures IN ('verified', 'not_checked')",
            name="ck_wp_generation_spine_figures",
        ),
    )
    op.create_index("ix_wp_generation_wp_id", "wp_generation", ["wp_id"])
    # One paper per run (spec 3C): a run id is unique within its source when given.
    op.create_index(
        "uq_wp_generation_source_run",
        "wp_generation",
        ["source", "run_id"],
        unique=True,
        postgresql_where=sa.text("run_id IS NOT NULL"),
    )
    op.execute(
        "CREATE TRIGGER trg_wp_generation_append_only BEFORE UPDATE OR DELETE ON wp_generation "
        "FOR EACH ROW EXECUTE FUNCTION oak_binder_append_only()"
    )
    op.execute(
        "CREATE TRIGGER trg_wp_generation_no_truncate BEFORE TRUNCATE ON wp_generation "
        "FOR EACH STATEMENT EXECUTE FUNCTION oak_binder_append_only()"
    )
    op.execute(GRANTS)


def downgrade() -> None:
    op.drop_index("uq_wp_generation_source_run", table_name="wp_generation")
    op.drop_index("ix_wp_generation_wp_id", table_name="wp_generation")
    op.drop_table("wp_generation")
