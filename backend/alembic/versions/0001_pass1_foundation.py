"""Pass 1 foundation: binder, wp, wp_version, wp_attachment; wp_version is append-only.

Revision ID: 0001
Revises:
Create Date: 2026-10-28

This file is a frozen snapshot. It deliberately repeats the constraint SQL from the models
instead of importing it, so a later change to the models cannot silently rewrite history.
tests/test_migration_sql.py checks that the two agree.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SHA256_HEX = "~ '^[0-9a-f]{64}$'"
TEMPLATES = "'statutory', 'tax_audit', 'bank_branch', 'internal'"
BINDER_STATES = "'open', 'assembled'"
WP_STATUSES = "'draft', 'prepared', 'in_review', 'reviewed', 'signed_off'"
SECTIONS = (
    "'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', "
    "'R', 'S', 'T', 'W', 'X', 'Z'"
)

# Spec 4, "Append-only: wp_version ... Updates and deletes fail at the database."
# The function raises for any UPDATE, DELETE or TRUNCATE, whoever runs it. The error code is
# integrity_constraint_violation so drivers report it as an integrity error.
APPEND_ONLY_FUNCTION = """
CREATE FUNCTION oak_binder_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% is append-only: % is not allowed (SA 230; architecture D6)',
        TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'integrity_constraint_violation';
END
$$
"""

# Table rights for the application role. The role is cluster-wide and created by
# scripts/db/02_create.sql; the IF EXISTS keeps the migration valid on a cluster without it.
# wp_version gets SELECT and INSERT only: the second layer of append-only (architecture D6).
GRANTS = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'oak_binder_app') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON binder, wp, wp_attachment TO oak_binder_app;
        GRANT SELECT, INSERT ON wp_version TO oak_binder_app;
    END IF;
END
$$
"""


def upgrade() -> None:
    op.create_table(
        "binder",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("engagement", sa.Text(), nullable=False),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column("report_date", sa.Date(), nullable=True),
        sa.Column("assembly_due", sa.Date(), nullable=True),
        sa.Column("assembled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assembly_hash", sa.Text(), nullable=True),
        sa.Column("retention_until", sa.Date(), nullable=True),
        sa.Column("state", sa.Text(), server_default="open", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_binder"),
        sa.UniqueConstraint("engagement", name="uq_binder_engagement"),
        sa.CheckConstraint("btrim(engagement) <> ''", name="ck_binder_engagement_not_blank"),
        sa.CheckConstraint(f"template IN ({TEMPLATES})", name="ck_binder_template"),
        sa.CheckConstraint(f"state IN ({BINDER_STATES})", name="ck_binder_state"),
        # Explicit IS NOT NULL on every column: a CHECK lets an "unknown" comparison through.
        sa.CheckConstraint(
            "(report_date IS NULL AND assembly_due IS NULL AND retention_until IS NULL) OR "
            "(report_date IS NOT NULL AND assembly_due IS NOT NULL AND retention_until IS NOT NULL "
            "AND assembly_due = report_date + 60 AND "
            "retention_until = (report_date + INTERVAL '7 years')::date)",
            name="ck_binder_report_clocks",
        ),
        sa.CheckConstraint(
            "(state = 'open' AND assembled_at IS NULL AND assembly_hash IS NULL) OR "
            "(state = 'assembled' AND report_date IS NOT NULL AND assembled_at IS NOT NULL AND "
            f"assembly_hash IS NOT NULL AND assembly_hash {SHA256_HEX})",
            name="ck_binder_assembly",
        ),
    )

    op.create_table(
        "wp",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("binder_id", sa.Uuid(), nullable=False),
        sa.Column("ref", sa.Text(), nullable=False),
        sa.Column("section", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column(
            "sa_refs", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False
        ),
        sa.Column("objective", sa.Text(), nullable=True),
        sa.Column("procedure", sa.Text(), nullable=True),
        sa.Column("population_sample", sa.Text(), nullable=True),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("conclusion", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default="draft", nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_wp"),
        sa.ForeignKeyConstraint(
            ["binder_id"], ["binder.id"], name="fk_wp_binder", ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("binder_id", "ref", name="uq_wp_binder_ref"),
        sa.CheckConstraint("btrim(ref) <> ''", name="ck_wp_ref_not_blank"),
        sa.CheckConstraint(f"section IN ({SECTIONS})", name="ck_wp_section"),
        sa.CheckConstraint(f"status IN ({WP_STATUSES})", name="ck_wp_status"),
        sa.CheckConstraint(
            "status <> 'signed_off' OR (conclusion IS NOT NULL AND btrim(conclusion) <> '')",
            name="ck_wp_signed_off_has_conclusion",
        ),
        sa.CheckConstraint(
            "current_version IS NULL OR current_version >= 1", name="ck_wp_current_version"
        ),
        sa.CheckConstraint(
            "status = 'draft' OR current_version IS NOT NULL", name="ck_wp_status_needs_version"
        ),
    )

    op.create_table(
        "wp_version",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("wp_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("body", postgresql.JSONB(), nullable=False),
        sa.Column("prepared_by", sa.Text(), nullable=False),
        sa.Column("prepared_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_by", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("signed_off_by", sa.Text(), nullable=True),
        sa.Column("signed_off_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("amendment_reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_wp_version"),
        sa.ForeignKeyConstraint(["wp_id"], ["wp.id"], name="fk_wp_version_wp", ondelete="RESTRICT"),
        sa.UniqueConstraint("wp_id", "version", name="uq_wp_version_wp_version"),
        sa.CheckConstraint("version >= 1", name="ck_wp_version_positive"),
        sa.CheckConstraint("btrim(prepared_by) <> ''", name="ck_wp_version_prepared_by_not_blank"),
        sa.CheckConstraint(
            "(reviewed_by IS NULL) = (reviewed_at IS NULL)", name="ck_wp_version_review_pair"
        ),
        sa.CheckConstraint(
            "(signed_off_by IS NULL) = (signed_off_at IS NULL)",
            name="ck_wp_version_sign_off_pair",
        ),
        sa.CheckConstraint(
            "signed_off_by IS NULL OR reviewed_by IS NOT NULL",
            name="ck_wp_version_sign_off_needs_review",
        ),
        sa.CheckConstraint(f"content_hash {SHA256_HEX}", name="ck_wp_version_content_hash"),
    )

    # wp.current_version must name a real version of that paper. Added after both tables
    # exist because they reference each other.
    op.create_foreign_key(
        "fk_wp_current_version",
        "wp",
        "wp_version",
        ["id", "current_version"],
        ["wp_id", "version"],
        ondelete="RESTRICT",
    )

    op.create_table(
        "wp_attachment",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("wp_version_id", sa.Uuid(), nullable=False),
        sa.Column("vault_doc_id", sa.Text(), nullable=False),
        sa.Column("identifying_chars", sa.Text(), nullable=True),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("media_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_wp_attachment"),
        sa.ForeignKeyConstraint(
            ["wp_version_id"],
            ["wp_version.id"],
            name="fk_wp_attachment_wp_version",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("wp_version_id", "sha256", name="uq_wp_attachment_version_sha256"),
        sa.CheckConstraint(f"sha256 {SHA256_HEX}", name="ck_wp_attachment_sha256"),
        sa.CheckConstraint("btrim(filename) <> ''", name="ck_wp_attachment_filename_not_blank"),
        sa.CheckConstraint("size_bytes >= 0", name="ck_wp_attachment_size"),
    )

    op.execute(APPEND_ONLY_FUNCTION)
    op.execute(
        "CREATE TRIGGER trg_wp_version_append_only BEFORE UPDATE OR DELETE ON wp_version "
        "FOR EACH ROW EXECUTE FUNCTION oak_binder_append_only()"
    )
    op.execute(
        "CREATE TRIGGER trg_wp_version_no_truncate BEFORE TRUNCATE ON wp_version "
        "FOR EACH STATEMENT EXECUTE FUNCTION oak_binder_append_only()"
    )
    op.execute(GRANTS)


def downgrade() -> None:
    # Dropping a table is not an UPDATE or DELETE on its rows, so the trigger does not fire.
    # This exists for the test database's rebuild; a live audit file is never downgraded.
    op.drop_table("wp_attachment")
    # The circular key must go before wp_version. IF EXISTS keeps the downgrade valid on a
    # database that was built before this key was part of the migration.
    op.execute("ALTER TABLE wp DROP CONSTRAINT IF EXISTS fk_wp_current_version")
    op.drop_table("wp_version")
    op.drop_table("wp")
    op.drop_table("binder")
    op.execute("DROP FUNCTION IF EXISTS oak_binder_append_only()")
