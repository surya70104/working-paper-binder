"""Stage 6: attachments belong to papers, binder events, purged state.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-29

A new migration rather than an edit of 0001, because 0001 is applied to a database that
holds data (D17). Every step is reversible; the downgrade is rendered by the offline SQL
test and is not run against data.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SHA256_HEX = "~ '^[0-9a-f]{64}$'"
BINDER_STATES = "'open', 'assembled', 'purged'"
EVENT_KINDS = "'assembled', 'amended', 'purged', 'produced'"

ASSEMBLY_CHECK = (
    "(state = 'open' AND assembled_at IS NULL AND assembly_hash IS NULL) OR "
    "(state IN ('assembled', 'purged') AND report_date IS NOT NULL AND "
    "assembled_at IS NOT NULL AND assembly_hash IS NOT NULL AND "
    f"assembly_hash {SHA256_HEX})"
)
ASSEMBLY_CHECK_0001 = (
    "(state = 'open' AND assembled_at IS NULL AND assembly_hash IS NULL) OR "
    "(state = 'assembled' AND report_date IS NOT NULL AND assembled_at IS NOT NULL AND "
    f"assembly_hash IS NOT NULL AND assembly_hash {SHA256_HEX})"
)

GRANTS = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'oak_binder_app') THEN
        GRANT SELECT, INSERT ON binder_event TO oak_binder_app;
    END IF;
END
$$
"""


def upgrade() -> None:
    # --- wp_attachment: owned by the paper, linked to a version at the next prepare -------
    op.add_column("wp_attachment", sa.Column("wp_id", sa.Uuid(), nullable=True))
    op.execute(
        "UPDATE wp_attachment a SET wp_id = v.wp_id "
        "FROM wp_version v WHERE a.wp_version_id = v.id AND a.wp_id IS NULL"
    )
    op.alter_column("wp_attachment", "wp_id", nullable=False)
    op.alter_column("wp_attachment", "wp_version_id", nullable=True)
    op.add_column(
        "wp_attachment",
        sa.Column("attached_by", sa.Text(), nullable=False, server_default="unknown"),
    )
    op.add_column(
        "wp_attachment",
        sa.Column(
            "attached_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.alter_column("wp_attachment", "attached_by", server_default=None)
    op.alter_column("wp_attachment", "attached_at", server_default=None)
    op.create_foreign_key(
        "fk_wp_attachment_wp", "wp_attachment", "wp", ["wp_id"], ["id"], ondelete="RESTRICT"
    )
    op.drop_constraint("uq_wp_attachment_version_sha256", "wp_attachment", type_="unique")
    op.create_unique_constraint("uq_wp_attachment_wp_sha256", "wp_attachment", ["wp_id", "sha256"])

    # --- binder: the purged state ---------------------------------------------------------
    op.drop_constraint("ck_binder_state", "binder", type_="check")
    op.create_check_constraint("ck_binder_state", "binder", f"state IN ({BINDER_STATES})")
    op.drop_constraint("ck_binder_assembly", "binder", type_="check")
    op.create_check_constraint("ck_binder_assembly", "binder", ASSEMBLY_CHECK)

    # --- binder_event: append-only record of assembly, amendment, purge, production -------
    op.create_table(
        "binder_event",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("binder_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "details", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_binder_event"),
        sa.ForeignKeyConstraint(
            ["binder_id"], ["binder.id"], name="fk_binder_event_binder", ondelete="RESTRICT"
        ),
        sa.CheckConstraint(f"kind IN ({EVENT_KINDS})", name="ck_binder_event_kind"),
        sa.CheckConstraint("btrim(actor) <> ''", name="ck_binder_event_actor_not_blank"),
    )
    op.execute(
        "CREATE TRIGGER trg_binder_event_append_only BEFORE UPDATE OR DELETE ON binder_event "
        "FOR EACH ROW EXECUTE FUNCTION oak_binder_append_only()"
    )
    op.execute(
        "CREATE TRIGGER trg_binder_event_no_truncate BEFORE TRUNCATE ON binder_event "
        "FOR EACH STATEMENT EXECUTE FUNCTION oak_binder_append_only()"
    )
    op.execute(GRANTS)


def downgrade() -> None:
    op.drop_table("binder_event")
    op.drop_constraint("ck_binder_assembly", "binder", type_="check")
    op.create_check_constraint("ck_binder_assembly", "binder", ASSEMBLY_CHECK_0001)
    op.drop_constraint("ck_binder_state", "binder", type_="check")
    op.create_check_constraint("ck_binder_state", "binder", "state IN ('open', 'assembled')")
    op.drop_constraint("uq_wp_attachment_wp_sha256", "wp_attachment", type_="unique")
    op.create_unique_constraint(
        "uq_wp_attachment_version_sha256", "wp_attachment", ["wp_version_id", "sha256"]
    )
    op.drop_constraint("fk_wp_attachment_wp", "wp_attachment", type_="foreignkey")
    op.drop_column("wp_attachment", "attached_at")
    op.drop_column("wp_attachment", "attached_by")
    # Rows never linked to a version cannot survive a downgrade to the 0001 shape.
    op.execute("DELETE FROM wp_attachment WHERE wp_version_id IS NULL")
    op.alter_column("wp_attachment", "wp_version_id", nullable=False)
    op.drop_column("wp_attachment", "wp_id")
