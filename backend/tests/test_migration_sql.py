"""Migration 0001 rendered offline: no database, no connection.

The URL points at a host that does not exist, so if Alembic ever tried to connect, these
tests would fail instead of quietly passing.
"""

from __future__ import annotations

import io
import re
from functools import cache

import pytest
from alembic import command
from sqlalchemy import ForeignKeyConstraint

from oak_binder.db import Base
from tests.conftest import alembic_config

NOWHERE = "postgresql+psycopg://oak_binder_owner:x@nowhere.invalid:5432/oak_binder_test"
ELSEWHERE = "postgresql+psycopg://oak_owner:x@nowhere.invalid:5432/oak_spine"


@cache
def rendered(direction: str) -> str:
    buffer = io.StringIO()
    cfg = alembic_config(NOWHERE, output=buffer)
    if direction == "upgrade":
        command.upgrade(cfg, "head", sql=True)
    else:
        command.downgrade(cfg, "head:base", sql=True)
    return buffer.getvalue()


def table_block(sql: str, table: str) -> str:
    start = sql.index(f"CREATE TABLE {table} (")
    return sql[start : sql.index(";", start)]


def test_upgrade_creates_every_model_table_with_every_column() -> None:
    # A column is either in the CREATE TABLE block (its first migration) or added later by
    # ALTER TABLE ... ADD COLUMN (a following migration). Both count; absence does not.
    sql = rendered("upgrade")
    for table in Base.metadata.tables.values():
        block = table_block(sql, table.name)
        for column in table.columns:
            in_block = re.search(rf"^\s+{re.escape(column.name)} [A-Z]", block, re.M)
            added = f"ALTER TABLE {table.name} ADD COLUMN {column.name} " in sql
            assert in_block or added, f"{table.name}.{column.name} not in any migration"


def test_upgrade_declares_every_named_model_constraint() -> None:
    sql = rendered("upgrade")
    for table in Base.metadata.tables.values():
        block = table_block(sql, table.name)
        for constraint in table.constraints:
            name = constraint.name
            if not isinstance(name, str):
                continue
            in_block = name in block
            added = f"ALTER TABLE {table.name} ADD CONSTRAINT {name} " in sql
            if isinstance(constraint, ForeignKeyConstraint) and constraint.use_alter:
                assert added, f"{name} must be added by ALTER TABLE"
            else:
                assert in_block or added, f"{name} missing from every migration"


def test_wp_version_is_append_only_at_the_database() -> None:
    sql = rendered("upgrade")
    assert "CREATE FUNCTION oak_binder_append_only() RETURNS trigger" in sql
    assert "USING ERRCODE = 'integrity_constraint_violation'" in sql
    assert (
        "CREATE TRIGGER trg_wp_version_append_only BEFORE UPDATE OR DELETE ON wp_version "
        "FOR EACH ROW EXECUTE FUNCTION oak_binder_append_only()"
    ) in sql
    assert (
        "CREATE TRIGGER trg_wp_version_no_truncate BEFORE TRUNCATE ON wp_version "
        "FOR EACH STATEMENT EXECUTE FUNCTION oak_binder_append_only()"
    ) in sql


def test_application_role_gets_insert_but_never_update_or_delete_on_wp_version() -> None:
    sql = rendered("upgrade")
    assert "GRANT SELECT, INSERT ON wp_version TO oak_binder_app" in sql
    assert (
        "GRANT SELECT, INSERT, UPDATE, DELETE ON binder, wp, wp_attachment TO oak_binder_app" in sql
    )
    for line in sql.splitlines():
        if "GRANT" in line and "wp_version" in line:
            assert "UPDATE" not in line and "DELETE" not in line


def test_binder_event_is_append_only_at_the_database() -> None:
    sql = rendered("upgrade")
    assert (
        "CREATE TRIGGER trg_binder_event_append_only BEFORE UPDATE OR DELETE ON binder_event "
        "FOR EACH ROW EXECUTE FUNCTION oak_binder_append_only()"
    ) in sql
    assert "CREATE TRIGGER trg_binder_event_no_truncate BEFORE TRUNCATE ON binder_event" in sql
    assert "GRANT SELECT, INSERT ON binder_event TO oak_binder_app" in sql
    for line in sql.splitlines():
        if "GRANT" in line and "binder_event" in line:
            assert "UPDATE" not in line and "DELETE" not in line


def test_review_note_is_append_only_at_the_database() -> None:
    sql = rendered("upgrade")
    assert (
        "CREATE TRIGGER trg_review_note_append_only BEFORE UPDATE OR DELETE ON review_note "
        "FOR EACH ROW EXECUTE FUNCTION oak_binder_append_only()"
    ) in sql
    assert "CREATE TRIGGER trg_review_note_no_truncate BEFORE TRUNCATE ON review_note" in sql
    assert "GRANT SELECT, INSERT ON review_note TO oak_binder_app" in sql
    for line in sql.splitlines():
        if "GRANT" in line and "review_note" in line:
            assert "UPDATE" not in line and "DELETE" not in line


def test_downgrade_removes_everything_it_created() -> None:
    sql = rendered("downgrade")
    for table in ("review_note", "binder_event", "wp_attachment", "wp_version", "wp", "binder"):
        assert f"DROP TABLE {table};" in sql
    # 0002 is reversed before 0001: the event table goes first.
    assert sql.index("DROP TABLE binder_event;") < sql.index("DROP TABLE wp_attachment;")
    assert "DROP FUNCTION IF EXISTS oak_binder_append_only()" in sql
    # The circular key is dropped before the table it points at.
    assert sql.index("fk_wp_current_version") < sql.index("DROP TABLE wp_version;")


def test_migration_refuses_any_database_but_the_binders() -> None:
    cfg = alembic_config(ELSEWHERE, output=io.StringIO())
    with pytest.raises(ValueError, match="never connects to any other database"):
        command.upgrade(cfg, "head", sql=True)
