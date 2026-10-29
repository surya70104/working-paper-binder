"""Database rules added by migration 0002, against oak_binder_test: binder_event is
append-only, the purged state keeps its assembly record, attachments may precede versions."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

import pytest
from sqlalchemy import Connection, delete, insert, select, text, update
from sqlalchemy.exc import IntegrityError, ProgrammingError

from oak_binder.models import Binder, BinderEvent, Wp, WpAttachment
from tests.conftest import unique

pytestmark = pytest.mark.db

HASH = "0" * 64
DATED: dict[str, Any] = {
    "report_date": date(2026, 9, 30),
    "assembly_due": date(2026, 11, 29),
    "retention_until": date(2033, 9, 30),
}


def binder(db: Connection, **extra: Any) -> uuid.UUID:
    row = db.execute(
        insert(Binder)
        .values(engagement=unique("ENG"), template="statutory", **extra)
        .returning(Binder.id)
    )
    result: uuid.UUID = row.scalar_one()
    return result


def event(db: Connection, binder_id: uuid.UUID, **extra: Any) -> uuid.UUID:
    values: dict[str, Any] = {
        "binder_id": binder_id,
        "kind": "assembled",
        "actor": "partner@firm",
        "at": datetime.now(UTC),
        "details": {"file_hash": HASH},
    }
    values.update(extra)
    row = db.execute(insert(BinderEvent).values(**values).returning(BinderEvent.id))
    result: uuid.UUID = row.scalar_one()
    return result


def test_binder_event_is_append_only(db: Connection) -> None:
    event_id = event(db, binder(db))
    with (
        pytest.raises(IntegrityError, match="binder_event is append-only: UPDATE"),
        db.begin_nested(),
    ):
        db.execute(update(BinderEvent).where(BinderEvent.id == event_id).values(actor="x"))
    with (
        pytest.raises(IntegrityError, match="binder_event is append-only: DELETE"),
        db.begin_nested(),
    ):
        db.execute(delete(BinderEvent).where(BinderEvent.id == event_id))
    with (
        pytest.raises(IntegrityError, match="binder_event is append-only: TRUNCATE"),
        db.begin_nested(),
    ):
        db.execute(text("TRUNCATE binder_event"))
    assert db.execute(select(BinderEvent.id).where(BinderEvent.id == event_id)).scalar_one()


def test_event_kind_and_actor_are_checked(db: Connection) -> None:
    binder_id = binder(db)
    with pytest.raises(IntegrityError, match="ck_binder_event_kind"), db.begin_nested():
        event(db, binder_id, kind="opened")
    with pytest.raises(IntegrityError, match="ck_binder_event_actor_not_blank"), db.begin_nested():
        event(db, binder_id, actor="  ")


def test_application_role_cannot_update_or_delete_events(app_db: Connection) -> None:
    for statement in (
        "UPDATE binder_event SET actor = 'x' WHERE false",
        "DELETE FROM binder_event WHERE false",
    ):
        with pytest.raises(ProgrammingError, match="permission denied"), app_db.begin_nested():
            app_db.execute(text(statement))
    app_db.execute(text("SELECT count(*) FROM binder_event")).scalar_one()


def test_purged_keeps_the_assembly_record(db: Connection) -> None:
    now = datetime.now(UTC)
    with pytest.raises(IntegrityError, match="ck_binder_assembly"), db.begin_nested():
        binder(db, state="purged", **DATED)  # purged without ever being assembled
    with pytest.raises(IntegrityError, match="ck_binder_assembly"), db.begin_nested():
        binder(db, state="purged", assembled_at=now, **DATED)  # no hash
    binder(db, state="purged", assembled_at=now, assembly_hash=HASH, **DATED)
    # An unknown state breaks both the state list and the assembly rule; PostgreSQL names
    # whichever it evaluates first, and either is the right refusal.
    with pytest.raises(IntegrityError, match="ck_binder_(state|assembly)"), db.begin_nested():
        binder(db, state="destroyed")


def test_an_attachment_may_precede_any_version(db: Connection) -> None:
    binder_id = binder(db)
    wp_id = db.execute(
        insert(Wp)
        .values(binder_id=binder_id, ref="D-1", section="D", title="Cash")
        .returning(Wp.id)
    ).scalar_one()
    values: dict[str, Any] = {
        "wp_id": wp_id,
        "wp_version_id": None,
        "vault_doc_id": HASH,
        "sha256": HASH,
        "filename": "a.csv",
        "media_type": "text/csv",
        "size_bytes": 3,
        "attached_by": "preparer@firm",
        "attached_at": datetime.now(UTC),
    }
    db.execute(insert(WpAttachment).values(**values))
    with pytest.raises(IntegrityError, match="uq_wp_attachment_wp_sha256"), db.begin_nested():
        db.execute(insert(WpAttachment).values(**values))  # same bytes on the same paper
