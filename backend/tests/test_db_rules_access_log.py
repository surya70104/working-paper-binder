"""Database rules added by migration 0004, against oak_binder_test: access_log is append-only,
never blank, and the application role can only read and insert it."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import Connection, delete, insert, select, text, update
from sqlalchemy.exc import IntegrityError, ProgrammingError

from oak_binder.models import AccessLog, Binder
from tests.conftest import unique

pytestmark = pytest.mark.db


def binder(db: Connection) -> uuid.UUID:
    result: uuid.UUID = db.execute(
        insert(Binder).values(engagement=unique("ENG"), template="statutory").returning(Binder.id)
    ).scalar_one()
    return result


def row(db: Connection, binder_id: uuid.UUID, **extra: Any) -> uuid.UUID:
    values: dict[str, Any] = {
        "binder_id": binder_id,
        "user": "partner@firm",
        "action": "binder",
        "at": datetime.now(UTC),
    }
    values.update(extra)
    result: uuid.UUID = db.execute(
        insert(AccessLog).values(**values).returning(AccessLog.id)
    ).scalar_one()
    return result


def test_access_log_is_append_only(db: Connection) -> None:
    access_id = row(db, binder(db))
    with (
        pytest.raises(IntegrityError, match="access_log is append-only: UPDATE"),
        db.begin_nested(),
    ):
        db.execute(update(AccessLog).where(AccessLog.id == access_id).values(user="someone"))
    with (
        pytest.raises(IntegrityError, match="access_log is append-only: DELETE"),
        db.begin_nested(),
    ):
        db.execute(delete(AccessLog).where(AccessLog.id == access_id))
    with (
        pytest.raises(IntegrityError, match="access_log is append-only: TRUNCATE"),
        db.begin_nested(),
    ):
        db.execute(text("TRUNCATE access_log"))
    assert db.execute(select(AccessLog.user).where(AccessLog.id == access_id)).scalar_one() == (
        "partner@firm"
    )


def test_access_log_names_a_user_and_an_action(db: Connection) -> None:
    binder_id = binder(db)
    with pytest.raises(IntegrityError, match="ck_access_log_user_not_blank"), db.begin_nested():
        row(db, binder_id, user="   ")
    with pytest.raises(IntegrityError, match="ck_access_log_action_not_blank"), db.begin_nested():
        row(db, binder_id, action="")
    with pytest.raises(IntegrityError, match="fk_access_log_binder"), db.begin_nested():
        row(db, uuid.uuid4())


def test_binder_with_access_rows_cannot_be_deleted(db: Connection) -> None:
    binder_id = binder(db)
    row(db, binder_id)
    with pytest.raises(IntegrityError, match="fk_access_log_binder"), db.begin_nested():
        db.execute(delete(Binder).where(Binder.id == binder_id))


def test_application_role_cannot_rewrite_the_access_log(app_db: Connection) -> None:
    for statement in (
        "UPDATE access_log SET \"user\" = 'x' WHERE false",
        "DELETE FROM access_log WHERE false",
    ):
        with pytest.raises(ProgrammingError, match="permission denied"), app_db.begin_nested():
            app_db.execute(text(statement))
    app_db.execute(text("SELECT count(*) FROM access_log")).scalar_one()
