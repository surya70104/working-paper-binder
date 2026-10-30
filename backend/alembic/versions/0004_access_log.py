"""Access log: who opened the file after assembly, append-only (spec 3H, 4).

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-30

Additive: one new table, its index, triggers and grants. Nothing existing is touched.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GRANTS = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'oak_binder_app') THEN
        GRANT SELECT, INSERT ON access_log TO oak_binder_app;
    END IF;
END
$$
"""


def upgrade() -> None:
    op.create_table(
        "access_log",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("binder_id", sa.Uuid(), nullable=False),
        sa.Column("user", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_access_log"),
        sa.ForeignKeyConstraint(
            ["binder_id"], ["binder.id"], name="fk_access_log_binder", ondelete="RESTRICT"
        ),
        sa.CheckConstraint("btrim(\"user\") <> ''", name="ck_access_log_user_not_blank"),
        sa.CheckConstraint("btrim(action) <> ''", name="ck_access_log_action_not_blank"),
    )
    op.create_index("ix_access_log_binder_id", "access_log", ["binder_id"])
    op.execute(
        "CREATE TRIGGER trg_access_log_append_only BEFORE UPDATE OR DELETE ON access_log "
        "FOR EACH ROW EXECUTE FUNCTION oak_binder_append_only()"
    )
    op.execute(
        "CREATE TRIGGER trg_access_log_no_truncate BEFORE TRUNCATE ON access_log "
        "FOR EACH STATEMENT EXECUTE FUNCTION oak_binder_append_only()"
    )
    op.execute(GRANTS)


def downgrade() -> None:
    op.drop_index("ix_access_log_binder_id", table_name="access_log")
    op.drop_table("access_log")
