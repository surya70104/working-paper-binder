"""Database rules added by migration 0006, against oak_binder_test: discussion and departure
are append-only, carry spec 4's fields, refuse blanks, and the application role can only
read and insert them."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

import pytest
from sqlalchemy import Connection, delete, insert, select, text, update
from sqlalchemy.exc import IntegrityError, ProgrammingError

from oak_binder.models import Binder, Departure, Discussion
from tests.conftest import unique

pytestmark = pytest.mark.db


def binder(db: Connection) -> uuid.UUID:
    result: uuid.UUID = db.execute(
        insert(Binder).values(engagement=unique("ENG"), template="statutory").returning(Binder.id)
    ).scalar_one()
    return result


def discussion(db: Connection, binder_id: uuid.UUID, **extra: Any) -> uuid.UUID:
    values: dict[str, Any] = {
        "binder_id": binder_id,
        "date": date(2026, 10, 30),
        "participants": ["A. Partner", "R. Mehta (TCWG, Audit Committee Chair)"],
        "matter": "Going concern assessment",
        "outcome": "Management to provide cash-flow forecast",
        "recorded_by": "partner@firm",
        "recorded_at": datetime.now(UTC),
    }
    values.update(extra)
    result: uuid.UUID = db.execute(
        insert(Discussion).values(**values).returning(Discussion.id)
    ).scalar_one()
    return result


def departure(db: Connection, binder_id: uuid.UUID, **extra: Any) -> uuid.UUID:
    values: dict[str, Any] = {
        "binder_id": binder_id,
        "requirement": "SA 505 external confirmation of bank balances",
        "reason": "Bank did not respond within the reporting timetable",
        "alternative_procedure": "Agreed closing balances to statements and subsequent receipts",
        "approved_by": "partner@firm",
        "recorded_by": "manager@firm",
        "recorded_at": datetime.now(UTC),
    }
    values.update(extra)
    result: uuid.UUID = db.execute(
        insert(Departure).values(**values).returning(Departure.id)
    ).scalar_one()
    return result


def test_both_logs_are_append_only(db: Connection) -> None:
    binder_id = binder(db)
    d_id = discussion(db, binder_id)
    p_id = departure(db, binder_id)
    for table, model, row_id, change in (
        ("discussion", Discussion, d_id, {"matter": "edited"}),
        ("departure", Departure, p_id, {"reason": "edited"}),
    ):
        with (
            pytest.raises(IntegrityError, match=f"{table} is append-only: UPDATE"),
            db.begin_nested(),
        ):
            db.execute(update(model).where(model.id == row_id).values(**change))
        with (
            pytest.raises(IntegrityError, match=f"{table} is append-only: DELETE"),
            db.begin_nested(),
        ):
            db.execute(delete(model).where(model.id == row_id))
        with (
            pytest.raises(IntegrityError, match=f"{table} is append-only: TRUNCATE"),
            db.begin_nested(),
        ):
            db.execute(text(f"TRUNCATE {table}"))
    assert db.execute(select(Discussion.matter).where(Discussion.id == d_id)).scalar_one() == (
        "Going concern assessment"
    )


def test_entries_carry_the_spec_fields_and_refuse_blanks(db: Connection) -> None:
    binder_id = binder(db)
    with pytest.raises(IntegrityError, match="ck_discussion_has_participants"), db.begin_nested():
        discussion(db, binder_id, participants=[])
    with pytest.raises(IntegrityError, match="ck_discussion_matter_not_blank"), db.begin_nested():
        discussion(db, binder_id, matter="  ")
    with (
        pytest.raises(IntegrityError, match="ck_discussion_recorded_by_not_blank"),
        db.begin_nested(),
    ):
        discussion(db, binder_id, recorded_by="")
    discussion(db, binder_id, outcome=None)  # the outcome may come later, as a new entry
    with (
        pytest.raises(IntegrityError, match="ck_departure_requirement_not_blank"),
        db.begin_nested(),
    ):
        departure(db, binder_id, requirement=" ")
    with pytest.raises(IntegrityError, match="ck_departure_reason_not_blank"), db.begin_nested():
        departure(db, binder_id, reason="")
    with (
        pytest.raises(IntegrityError, match="ck_departure_alternative_not_blank"),
        db.begin_nested(),
    ):
        departure(db, binder_id, alternative_procedure="")
    departure(db, binder_id, approved_by=None)  # approval may follow, as a new entry
    with pytest.raises(IntegrityError, match="fk_discussion_binder"), db.begin_nested():
        discussion(db, uuid.uuid4())


def test_a_binder_with_log_entries_cannot_be_deleted(db: Connection) -> None:
    binder_id = binder(db)
    departure(db, binder_id)
    with pytest.raises(IntegrityError, match="fk_departure_binder"), db.begin_nested():
        db.execute(delete(Binder).where(Binder.id == binder_id))


def test_application_role_cannot_rewrite_the_logs(app_db: Connection) -> None:
    for statement in (
        "UPDATE discussion SET matter = 'x' WHERE false",
        "DELETE FROM discussion WHERE false",
        "UPDATE departure SET reason = 'x' WHERE false",
        "DELETE FROM departure WHERE false",
    ):
        with pytest.raises(ProgrammingError, match="permission denied"), app_db.begin_nested():
            app_db.execute(text(statement))
    app_db.execute(text("SELECT count(*) FROM discussion")).scalar_one()
    app_db.execute(text("SELECT count(*) FROM departure")).scalar_one()
