"""Database rules added by migration 0008, against oak_binder_test: wp_generation is
append-only, names its source from spec 3C's five, refuses blanks and a malformed hash, keeps
one paper per run within a source, and the application role can only read and insert it."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import Connection, delete, insert, select, text, update
from sqlalchemy.exc import IntegrityError, ProgrammingError

from oak_binder.models import Binder, Wp, WpGeneration
from tests.conftest import unique

pytestmark = pytest.mark.db


def paper(db: Connection, ref: str = "D-3") -> uuid.UUID:
    binder_id = db.execute(
        insert(Binder).values(engagement=unique("ENG"), template="statutory").returning(Binder.id)
    ).scalar_one()
    result: uuid.UUID = db.execute(
        insert(Wp)
        .values(binder_id=binder_id, ref=ref, section="D", title=f"Paper {ref}")
        .returning(Wp.id)
    ).scalar_one()
    return result


def generation(db: Connection, wp_id: uuid.UUID, **extra: Any) -> uuid.UUID:
    values: dict[str, Any] = {
        "wp_id": wp_id,
        "source": "sampling",
        "module": "oak_sampling",
        "module_version": "example",
        "run_id": unique("run"),
        "generated_at": datetime.now(UTC),
        "received_by": "sampling@oak",
        "received_at": datetime.now(UTC),
        "payload": {
            "inputs": {"n": 60},
            "citations": ["x"],
            "sampling": {"formula": "f", "seed": 1},
        },
        "content_hash_at_intake": "a" * 64,
        "spine_figures": None,
    }
    values.update(extra)
    result: uuid.UUID = db.execute(
        insert(WpGeneration).values(**values).returning(WpGeneration.id)
    ).scalar_one()
    return result


def test_the_record_is_append_only(db: Connection) -> None:
    row_id = generation(db, paper(db))
    with (
        pytest.raises(IntegrityError, match="wp_generation is append-only: UPDATE"),
        db.begin_nested(),
    ):
        db.execute(update(WpGeneration).where(WpGeneration.id == row_id).values(module="edited"))
    with (
        pytest.raises(IntegrityError, match="wp_generation is append-only: DELETE"),
        db.begin_nested(),
    ):
        db.execute(delete(WpGeneration).where(WpGeneration.id == row_id))
    with (
        pytest.raises(IntegrityError, match="wp_generation is append-only: TRUNCATE"),
        db.begin_nested(),
    ):
        db.execute(text("TRUNCATE wp_generation"))
    assert (
        db.execute(select(WpGeneration.module).where(WpGeneration.id == row_id)).scalar_one()
        == "oak_sampling"
    )


def test_the_record_names_its_source_and_refuses_blanks(db: Connection) -> None:
    wp_id = paper(db)
    with pytest.raises(IntegrityError, match="ck_wp_generation_source"), db.begin_nested():
        generation(db, wp_id, source="spreadsheet")
    for source in ("materiality", "sampling", "analytical_review", "workmind", "spine"):
        generation(db, wp_id, source=source)
    with (
        pytest.raises(IntegrityError, match="ck_wp_generation_module_not_blank"),
        db.begin_nested(),
    ):
        generation(db, wp_id, module="  ")
    with (
        pytest.raises(IntegrityError, match="ck_wp_generation_run_id_not_blank"),
        db.begin_nested(),
    ):
        generation(db, wp_id, run_id="")
    with (
        pytest.raises(IntegrityError, match="ck_wp_generation_received_by_not_blank"),
        db.begin_nested(),
    ):
        generation(db, wp_id, received_by="")
    with pytest.raises(IntegrityError, match="ck_wp_generation_content_hash"), db.begin_nested():
        generation(db, wp_id, content_hash_at_intake="not-a-hash")
    with pytest.raises(IntegrityError, match="ck_wp_generation_spine_figures"), db.begin_nested():
        generation(db, wp_id, spine_figures="maybe")
    generation(db, wp_id, spine_figures="verified")
    generation(db, wp_id, spine_figures="not_checked")
    generation(db, wp_id, run_id=None, module_version=None)  # both optional
    with pytest.raises(IntegrityError, match="fk_wp_generation_wp"), db.begin_nested():
        generation(db, uuid.uuid4())


def test_one_paper_per_run_within_a_source(db: Connection) -> None:
    wp_id = paper(db)
    run = unique("run")
    generation(db, wp_id, run_id=run)
    with pytest.raises(IntegrityError, match="uq_wp_generation_source_run"), db.begin_nested():
        generation(db, paper(db, "D-4"), run_id=run)
    generation(db, paper(db, "D-5"), source="analytical_review", run_id=run)  # another module
    generation(db, paper(db, "D-6"), run_id=None)
    generation(db, paper(db, "D-7"), run_id=None)  # no run id never collides


def test_a_generated_paper_cannot_be_deleted(db: Connection) -> None:
    wp_id = paper(db)
    generation(db, wp_id)
    with pytest.raises(IntegrityError, match="fk_wp_generation_wp"), db.begin_nested():
        db.execute(delete(Wp).where(Wp.id == wp_id))


def test_application_role_cannot_rewrite_the_record(app_db: Connection) -> None:
    for statement in (
        "UPDATE wp_generation SET module = 'x' WHERE false",
        "DELETE FROM wp_generation WHERE false",
    ):
        with pytest.raises(ProgrammingError, match="permission denied"), app_db.begin_nested():
            app_db.execute(text(statement))
    app_db.execute(text("SELECT count(*) FROM wp_generation")).scalar_one()
