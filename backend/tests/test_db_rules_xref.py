"""Database rules added by migration 0005, against oak_binder_test: a cross-reference names
exactly one target, never itself, with a known direction; papers it touches cannot be
deleted."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import Connection, delete, insert, text
from sqlalchemy.exc import IntegrityError

from oak_binder.models import Binder, Wp, Xref
from tests.conftest import unique

pytestmark = pytest.mark.db


def papers(db: Connection) -> tuple[uuid.UUID, uuid.UUID]:
    binder_id = db.execute(
        insert(Binder).values(engagement=unique("ENG"), template="statutory").returning(Binder.id)
    ).scalar_one()
    ids = []
    for ref in ("D-1", "D-2"):
        ids.append(
            db.execute(
                insert(Wp)
                .values(binder_id=binder_id, ref=ref, section="D", title=f"Paper {ref}")
                .returning(Wp.id)
            ).scalar_one()
        )
    return ids[0], ids[1]


def row(db: Connection, from_wp: uuid.UUID, **extra: Any) -> uuid.UUID:
    values: dict[str, Any] = {
        "from_wp": from_wp,
        "direction": "to",
        "created_by": "preparer@firm",
        "created_at": datetime.now(UTC),
    }
    values.update(extra)
    result: uuid.UUID = db.execute(insert(Xref).values(**values).returning(Xref.id)).scalar_one()
    return result


def test_xref_names_exactly_one_target(db: Connection) -> None:
    a, b = papers(db)
    row(db, a, to_wp=b)
    row(db, a, to_fs_line="Revenue from operations")
    row(db, a, to_vault_doc="a" * 64)
    with pytest.raises(IntegrityError, match="ck_xref_one_target"), db.begin_nested():
        row(db, a)  # no target
    with pytest.raises(IntegrityError, match="ck_xref_one_target"), db.begin_nested():
        row(db, a, to_wp=b, to_fs_line="Revenue")  # two targets


def test_xref_rules(db: Connection) -> None:
    a, b = papers(db)
    with pytest.raises(IntegrityError, match="ck_xref_not_self"), db.begin_nested():
        row(db, a, to_wp=a)
    with pytest.raises(IntegrityError, match="ck_xref_direction"), db.begin_nested():
        row(db, a, to_wp=b, direction="sideways")
    with pytest.raises(IntegrityError, match="ck_xref_fs_line_not_blank"), db.begin_nested():
        row(db, a, to_fs_line="   ")
    with pytest.raises(IntegrityError, match="ck_xref_vault_doc_not_blank"), db.begin_nested():
        row(db, a, to_vault_doc="")
    with pytest.raises(IntegrityError, match="ck_xref_created_by_not_blank"), db.begin_nested():
        row(db, a, to_wp=b, created_by=" ")
    with pytest.raises(IntegrityError, match="fk_xref_to_wp"), db.begin_nested():
        row(db, a, to_wp=uuid.uuid4())


def test_a_referenced_paper_cannot_be_deleted_from_under_its_references(db: Connection) -> None:
    a, b = papers(db)
    row(db, a, to_wp=b)
    with pytest.raises(IntegrityError, match="fk_xref_to_wp"), db.begin_nested():
        db.execute(delete(Wp).where(Wp.id == b))
    with pytest.raises(IntegrityError, match="fk_xref_from_wp"), db.begin_nested():
        db.execute(delete(Wp).where(Wp.id == a))


def test_application_role_may_add_and_remove_references(app_db: Connection) -> None:
    # A reference is working data, not a sign-off record: the application role manages it,
    # and the service refuses changes once the binder is assembled.
    for right in ("INSERT", "UPDATE", "DELETE"):
        granted = app_db.execute(
            text("SELECT has_table_privilege('oak_binder_app', 'xref', :right)"),
            {"right": right},
        ).scalar_one()
        assert granted is True, right
