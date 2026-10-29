"""Database rules added by migration 0003, against oak_binder_test: review_note is
append-only, each state carries its field, the application role cannot rewrite history."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import Connection, delete, insert, select, text, update
from sqlalchemy.exc import IntegrityError, ProgrammingError

from oak_binder.models import Binder, ReviewNote, Wp
from tests.conftest import unique

pytestmark = pytest.mark.db


def paper(db: Connection) -> uuid.UUID:
    binder_id = db.execute(
        insert(Binder).values(engagement=unique("ENG"), template="statutory").returning(Binder.id)
    ).scalar_one()
    wp_id: uuid.UUID = db.execute(
        insert(Wp)
        .values(binder_id=binder_id, ref="D-1", section="D", title="Cash")
        .returning(Wp.id)
    ).scalar_one()
    return wp_id


def row(db: Connection, wp_id: uuid.UUID, **extra: Any) -> uuid.UUID:
    values: dict[str, Any] = {
        "note_id": uuid.uuid4(),
        "step": 1,
        "wp_id": wp_id,
        "state": "raised",
        "text": "Reconcile to the bank statement",
        "raised_by": "reviewer@firm",
        "actor": "reviewer@firm",
        "at": datetime.now(UTC),
    }
    values.update(extra)
    result: uuid.UUID = db.execute(
        insert(ReviewNote).values(**values).returning(ReviewNote.id)
    ).scalar_one()
    return result


def test_review_note_is_append_only(db: Connection) -> None:
    note_row = row(db, paper(db))
    with (
        pytest.raises(IntegrityError, match="review_note is append-only: UPDATE"),
        db.begin_nested(),
    ):
        db.execute(update(ReviewNote).where(ReviewNote.id == note_row).values(state="cleared"))
    with (
        pytest.raises(IntegrityError, match="review_note is append-only: DELETE"),
        db.begin_nested(),
    ):
        db.execute(delete(ReviewNote).where(ReviewNote.id == note_row))
    with (
        pytest.raises(IntegrityError, match="review_note is append-only: TRUNCATE"),
        db.begin_nested(),
    ):
        db.execute(text("TRUNCATE review_note"))
    assert db.execute(select(ReviewNote.id).where(ReviewNote.id == note_row)).scalar_one()


def test_each_state_carries_its_field(db: Connection) -> None:
    wp_id = paper(db)
    now = datetime.now(UTC)
    with pytest.raises(IntegrityError, match="ck_review_note_raised_has_text"), db.begin_nested():
        row(db, wp_id, text="   ")
    with (
        pytest.raises(IntegrityError, match="ck_review_note_assigned_has_assignee"),
        db.begin_nested(),
    ):
        row(db, wp_id, state="assigned", assigned_to=None)
    with pytest.raises(IntegrityError, match="ck_review_note_responded_at"), db.begin_nested():
        row(db, wp_id, state="responded")  # no responded_at
    with pytest.raises(IntegrityError, match="ck_review_note_responded_at"), db.begin_nested():
        row(db, wp_id, state="raised", responded_at=now)  # responded_at on a raised row
    with pytest.raises(IntegrityError, match="ck_review_note_cleared_by"), db.begin_nested():
        row(db, wp_id, state="cleared")  # no cleared_by
    with pytest.raises(IntegrityError, match="ck_review_note_state"), db.begin_nested():
        row(db, wp_id, state="ignored")
    row(db, wp_id, state="assigned", assigned_to="preparer@firm")
    row(db, wp_id, state="responded", responded_at=now)
    row(db, wp_id, state="cleared", cleared_by="reviewer@firm")


def test_steps_of_one_note_are_unique(db: Connection) -> None:
    wp_id = paper(db)
    note_id = uuid.uuid4()
    row(db, wp_id, note_id=note_id, step=1)
    with pytest.raises(IntegrityError, match="uq_review_note_note_step"), db.begin_nested():
        row(db, wp_id, note_id=note_id, step=1)
    row(db, wp_id, note_id=note_id, step=2, state="assigned", assigned_to="preparer@firm")


def test_application_role_cannot_rewrite_notes(app_db: Connection) -> None:
    for statement in (
        "UPDATE review_note SET state = 'cleared' WHERE false",
        "DELETE FROM review_note WHERE false",
    ):
        with pytest.raises(ProgrammingError, match="permission denied"), app_db.begin_nested():
            app_db.execute(text(statement))
    app_db.execute(text("SELECT count(*) FROM review_note")).scalar_one()
