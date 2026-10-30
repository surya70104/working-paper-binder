"""Cross-references between papers, Spine lines and documents (spec 3B, 3E, 4).

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-30

Additive: one new table, its indexes and grants. Nothing existing is touched. A reference is
plain data a preparer adds and removes while the binder is open, so the application role
gets the four ordinary rights; nothing about it is a sign-off record.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GRANTS = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'oak_binder_app') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON xref TO oak_binder_app;
    END IF;
END
$$
"""

ONE_TARGET = (
    "(CASE WHEN to_wp IS NOT NULL THEN 1 ELSE 0 END"
    " + CASE WHEN to_fs_line IS NOT NULL THEN 1 ELSE 0 END"
    " + CASE WHEN to_vault_doc IS NOT NULL THEN 1 ELSE 0 END) = 1"
)


def upgrade() -> None:
    op.create_table(
        "xref",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("from_wp", sa.Uuid(), nullable=False),
        sa.Column("to_wp", sa.Uuid(), nullable=True),
        sa.Column("to_fs_line", sa.Text(), nullable=True),
        sa.Column("to_vault_doc", sa.Text(), nullable=True),
        sa.Column("direction", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_xref"),
        sa.ForeignKeyConstraint(
            ["from_wp"], ["wp.id"], name="fk_xref_from_wp", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["to_wp"], ["wp.id"], name="fk_xref_to_wp", ondelete="RESTRICT"),
        sa.CheckConstraint(ONE_TARGET, name="ck_xref_one_target"),
        sa.CheckConstraint("to_wp IS NULL OR to_wp <> from_wp", name="ck_xref_not_self"),
        sa.CheckConstraint(
            "to_fs_line IS NULL OR btrim(to_fs_line) <> ''", name="ck_xref_fs_line_not_blank"
        ),
        sa.CheckConstraint(
            "to_vault_doc IS NULL OR btrim(to_vault_doc) <> ''",
            name="ck_xref_vault_doc_not_blank",
        ),
        sa.CheckConstraint("direction IN ('to', 'from')", name="ck_xref_direction"),
        sa.CheckConstraint("btrim(created_by) <> ''", name="ck_xref_created_by_not_blank"),
    )
    op.create_index("ix_xref_from_wp", "xref", ["from_wp"])
    op.create_index("ix_xref_to_wp", "xref", ["to_wp"])
    op.execute(GRANTS)


def downgrade() -> None:
    op.drop_index("ix_xref_to_wp", table_name="xref")
    op.drop_index("ix_xref_from_wp", table_name="xref")
    op.drop_table("xref")
