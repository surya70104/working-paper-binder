"""The rules the database itself enforces, run against oak_binder_test.

Skipped unless OAK_TEST_DATABASE_URL is set (see conftest). Every test runs inside a
transaction that is rolled back, so the test database is left as the migration made it.
Statements expected to fail run inside a savepoint (``begin_nested``) so the outer
transaction survives.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

import pytest
from alembic import command
from sqlalchemy import Connection, delete, insert, inspect, select, text, update
from sqlalchemy.exc import IntegrityError, ProgrammingError

from oak_binder.db import make_engine
from oak_binder.hashing import content_hash
from oak_binder.models import Binder, Wp, WpVersion
from tests.conftest import alembic_config, rebuild_allowed, unique

pytestmark = pytest.mark.db

REPORT_DATE = date(2026, 9, 30)
ASSEMBLY_DUE = date(2026, 11, 29)  # + 60 days
RETENTION_UNTIL = date(2033, 9, 30)  # + 7 years
HASH = "0" * 64


def new_binder(db: Connection, engagement: str | None = None, **extra: Any) -> uuid.UUID:
    row = db.execute(
        insert(Binder)
        .values(engagement=unique(engagement or "ENG"), template="statutory", **extra)
        .returning(Binder.id)
    )
    result: uuid.UUID = row.scalar_one()
    return result


def new_wp(db: Connection, binder_id: uuid.UUID, ref: str = "D-1", **extra: Any) -> uuid.UUID:
    values: dict[str, Any] = {"binder_id": binder_id, "ref": ref, "section": "D", "title": "Cash"}
    values.update(extra)
    row = db.execute(insert(Wp).values(**values).returning(Wp.id))
    result: uuid.UUID = row.scalar_one()
    return result


def new_version(db: Connection, wp_id: uuid.UUID, version: int = 1, **extra: Any) -> uuid.UUID:
    body = {"title": "Cash", "conclusion": "Fairly stated"}
    values: dict[str, Any] = {
        "wp_id": wp_id,
        "version": version,
        "body": body,
        "prepared_by": "preparer@firm",
        "prepared_at": datetime.now(UTC),
        "content_hash": content_hash(body),
    }
    values.update(extra)
    row = db.execute(insert(WpVersion).values(**values).returning(WpVersion.id))
    result: uuid.UUID = row.scalar_one()
    return result


def move_to(db: Connection, wp_id: uuid.UUID, **values: Any) -> None:
    db.execute(update(Wp).where(Wp.id == wp_id).values(**values))


# --- schema -----------------------------------------------------------------------------------


def test_migration_created_the_pass1_tables_and_triggers(db: Connection) -> None:
    tables = set(inspect(db).get_table_names())
    assert {"binder", "wp", "wp_version", "wp_attachment", "alembic_version"} <= tables
    triggers = (
        db.execute(
            text(
                "SELECT tgname FROM pg_trigger WHERE tgrelid = 'wp_version'::regclass "
                "AND NOT tgisinternal ORDER BY tgname"
            )
        )
        .scalars()
        .all()
    )
    assert triggers == ["trg_wp_version_append_only", "trg_wp_version_no_truncate"]


# --- wp_version is append-only (spec 4, architecture D6) --------------------------------------


def test_wp_version_update_is_refused(db: Connection) -> None:
    version_id = new_version(db, new_wp(db, new_binder(db)))
    with (
        pytest.raises(IntegrityError, match="wp_version is append-only: UPDATE"),
        db.begin_nested(),
    ):
        db.execute(update(WpVersion).where(WpVersion.id == version_id).values(amendment_reason="x"))


def test_wp_version_delete_is_refused(db: Connection) -> None:
    version_id = new_version(db, new_wp(db, new_binder(db)))
    with (
        pytest.raises(IntegrityError, match="wp_version is append-only: DELETE"),
        db.begin_nested(),
    ):
        db.execute(delete(WpVersion).where(WpVersion.id == version_id))
    assert db.execute(select(WpVersion.id).where(WpVersion.id == version_id)).scalar_one()


def test_wp_version_truncate_is_refused(db: Connection) -> None:
    new_version(db, new_wp(db, new_binder(db)))
    # wp_attachment, wp_review and wp (current_version) reference wp_version, and review_note,
    # xref and wp_generation reference wp, so PostgreSQL refuses "TRUNCATE wp_version" alone before
    # any trigger runs. Truncating them together passes that check and reaches the append-only
    # trigger, which is the point.
    with (
        pytest.raises(IntegrityError, match="wp_version is append-only: TRUNCATE"),
        db.begin_nested(),
    ):
        db.execute(
            text(
                "TRUNCATE wp_version, wp_attachment, wp_review, review_note, xref, "
                "wp_generation, wp"
            )
        )


def test_a_second_version_can_still_be_appended(db: Connection) -> None:
    wp_id = new_wp(db, new_binder(db))
    new_version(db, wp_id, 1)
    new_version(db, wp_id, 2, reviewed_by="reviewer@firm", reviewed_at=datetime.now(UTC))
    versions = db.execute(select(WpVersion.version).where(WpVersion.wp_id == wp_id)).scalars().all()
    assert sorted(versions) == [1, 2]


def test_other_tables_remain_editable(db: Connection) -> None:
    wp_id = new_wp(db, new_binder(db))
    db.execute(update(Wp).where(Wp.id == wp_id).values(title="Cash and bank"))
    assert db.execute(select(Wp.title).where(Wp.id == wp_id)).scalar_one() == "Cash and bank"


def test_a_paper_with_versions_cannot_be_deleted(db: Connection) -> None:
    wp_id = new_wp(db, new_binder(db))
    new_version(db, wp_id)
    with pytest.raises(IntegrityError, match="fk_wp_version_wp"), db.begin_nested():
        db.execute(delete(Wp).where(Wp.id == wp_id))


def test_application_role_lacks_update_and_delete_on_wp_version(app_db: Connection) -> None:
    for statement in (
        "UPDATE wp_version SET amendment_reason = 'x' WHERE false",
        "DELETE FROM wp_version WHERE false",
        "TRUNCATE wp_version",
    ):
        with pytest.raises(ProgrammingError, match="permission denied"), app_db.begin_nested():
            app_db.execute(text(statement))
    # The same role may read wp_version and edit the live paper.
    app_db.execute(text("SELECT count(*) FROM wp_version")).scalar_one()
    app_db.execute(text("UPDATE wp SET title = title WHERE false"))


# --- rules on the working paper (spec 3B, 8.1, 8.9) -------------------------------------------


def test_signed_off_requires_a_conclusion(db: Connection) -> None:
    wp_id = new_wp(db, new_binder(db), conclusion=None)
    new_version(db, wp_id, 1)
    for conclusion in (None, "", "   "):
        with (
            pytest.raises(IntegrityError, match="ck_wp_signed_off_has_conclusion"),
            db.begin_nested(),
        ):
            move_to(db, wp_id, status="signed_off", current_version=1, conclusion=conclusion)
    move_to(db, wp_id, status="signed_off", current_version=1, conclusion="Fairly stated")


def test_a_status_past_draft_needs_a_version(db: Connection) -> None:
    # Regression for the integrity gap: prepared/in_review/reviewed/signed_off are the
    # results of sign-offs, so a paper in those states must point at a version. The paper
    # has a conclusion so that only this rule is the one being broken.
    wp_id = new_wp(db, new_binder(db), conclusion="Fairly stated")
    for status in ("prepared", "in_review", "reviewed", "signed_off"):
        with (
            pytest.raises(IntegrityError, match="ck_wp_status_needs_version"),
            db.begin_nested(),
        ):
            move_to(db, wp_id, status=status, current_version=None)
    with pytest.raises(IntegrityError, match="ck_wp_status_needs_version"), db.begin_nested():
        new_wp(db, new_binder(db, "ENG-2"), ref="D-2", status="prepared")


def test_current_version_must_be_a_real_version_of_the_same_paper(db: Connection) -> None:
    binder_id = new_binder(db)
    first = new_wp(db, binder_id, ref="D-1")
    second = new_wp(db, binder_id, ref="D-2")
    new_version(db, first, 1)
    with pytest.raises(IntegrityError, match="fk_wp_current_version"), db.begin_nested():
        move_to(db, first, status="prepared", current_version=2)  # no such version
    with pytest.raises(IntegrityError, match="fk_wp_current_version"), db.begin_nested():
        move_to(db, second, status="prepared", current_version=1)  # another paper's version
    move_to(db, first, status="prepared", current_version=1)


def test_reference_is_unique_within_a_binder(db: Connection) -> None:
    first = new_binder(db, "ENG-1")
    second = new_binder(db, "ENG-2")
    new_wp(db, first, ref="D-1")
    with pytest.raises(IntegrityError, match="uq_wp_binder_ref"), db.begin_nested():
        new_wp(db, first, ref="D-1")
    new_wp(db, second, ref="D-1")  # another binder may use the same reference


def test_section_and_status_must_be_spec_values(db: Connection) -> None:
    binder_id = new_binder(db)
    with pytest.raises(IntegrityError, match="ck_wp_section"), db.begin_nested():
        new_wp(db, binder_id, section="U")
    with pytest.raises(IntegrityError, match="ck_wp_status"), db.begin_nested():
        new_wp(db, binder_id, status="approved")


def test_version_rules(db: Connection) -> None:
    wp_id = new_wp(db, new_binder(db))
    with pytest.raises(IntegrityError, match="ck_wp_version_content_hash"), db.begin_nested():
        new_version(db, wp_id, content_hash="not-a-hash")
    with pytest.raises(IntegrityError, match="ck_wp_version_review_pair"), db.begin_nested():
        new_version(db, wp_id, reviewed_by="reviewer@firm")  # without reviewed_at
    new_version(db, wp_id, 1)
    with pytest.raises(IntegrityError, match="uq_wp_version_wp_version"), db.begin_nested():
        new_version(db, wp_id, 1)


def test_sign_off_metadata_rules(db: Connection) -> None:
    # Spec 3D, 8.9: the signer and the time move together, and a sign-off presupposes a review.
    wp_id = new_wp(db, new_binder(db))
    now = datetime.now(UTC)
    reviewed: dict[str, Any] = {"reviewed_by": "reviewer@firm", "reviewed_at": now}
    with pytest.raises(IntegrityError, match="ck_wp_version_sign_off_pair"), db.begin_nested():
        new_version(db, wp_id, signed_off_by="partner@firm", **reviewed)
    with pytest.raises(IntegrityError, match="ck_wp_version_sign_off_pair"), db.begin_nested():
        new_version(db, wp_id, signed_off_at=now, **reviewed)
    with (
        pytest.raises(IntegrityError, match="ck_wp_version_sign_off_needs_review"),
        db.begin_nested(),
    ):
        new_version(db, wp_id, signed_off_by="partner@firm", signed_off_at=now)
    new_version(
        db,
        wp_id,
        reviewed_by="reviewer@firm",
        reviewed_at=now,
        signed_off_by="partner@firm",
        signed_off_at=now,
    )


# --- rules on the binder (spec 3F, 3G, 8.7) ---------------------------------------------------


def test_report_date_fixes_both_clocks(db: Connection) -> None:
    new_binder(
        db,
        "ENG-OK",
        report_date=REPORT_DATE,
        assembly_due=ASSEMBLY_DUE,
        retention_until=RETENTION_UNTIL,
    )
    with pytest.raises(IntegrityError, match="ck_binder_report_clocks"), db.begin_nested():
        new_binder(
            db,
            "ENG-SHORT",
            report_date=REPORT_DATE,
            assembly_due=ASSEMBLY_DUE,
            retention_until=date(2032, 9, 30),
        )
    with pytest.raises(IntegrityError, match="ck_binder_report_clocks"), db.begin_nested():
        new_binder(
            db,
            "ENG-LATE",
            report_date=REPORT_DATE,
            assembly_due=date(2026, 11, 30),
            retention_until=RETENTION_UNTIL,
        )
    with pytest.raises(IntegrityError, match="ck_binder_report_clocks"), db.begin_nested():
        new_binder(db, "ENG-NOCLOCK", report_date=REPORT_DATE)


def test_report_date_cannot_leave_a_clock_empty(db: Connection) -> None:
    # Regression: "assembly_due = report_date + 60" is "unknown" when assembly_due is NULL,
    # and a CHECK constraint accepts "unknown". Each missing combination must be refused.
    for missing in (
        {"report_date": REPORT_DATE},
        {"report_date": REPORT_DATE, "assembly_due": ASSEMBLY_DUE},
        {"report_date": REPORT_DATE, "retention_until": RETENTION_UNTIL},
        {"assembly_due": ASSEMBLY_DUE},
        {"retention_until": RETENTION_UNTIL},
        {"assembly_due": ASSEMBLY_DUE, "retention_until": RETENTION_UNTIL},
    ):
        with pytest.raises(IntegrityError, match="ck_binder_report_clocks"), db.begin_nested():
            new_binder(db, "ENG-PARTIAL", **missing)


def test_assembled_binder_cannot_have_an_empty_hash(db: Connection) -> None:
    # Regression: "NULL ~ pattern" is "unknown", which a CHECK constraint accepts.
    dated = {
        "report_date": REPORT_DATE,
        "assembly_due": ASSEMBLY_DUE,
        "retention_until": RETENTION_UNTIL,
    }
    with pytest.raises(IntegrityError, match="ck_binder_assembly"), db.begin_nested():
        new_binder(db, "ENG-NOHASH", state="assembled", assembled_at=datetime.now(UTC), **dated)
    with pytest.raises(IntegrityError, match="ck_binder_assembly"), db.begin_nested():
        new_binder(db, "ENG-NOTIME", state="assembled", assembly_hash=HASH, **dated)
    with pytest.raises(IntegrityError, match="ck_binder_assembly"), db.begin_nested():
        new_binder(
            db,
            "ENG-BADHASH",
            state="assembled",
            assembled_at=datetime.now(UTC),
            assembly_hash="not-a-hash",
            **dated,
        )


def test_assembled_means_dated_timestamped_and_hashed(db: Connection) -> None:
    with pytest.raises(IntegrityError, match="ck_binder_assembly"), db.begin_nested():
        new_binder(db, "ENG-A", state="assembled")
    with pytest.raises(IntegrityError, match="ck_binder_assembly"), db.begin_nested():
        new_binder(
            db, "ENG-B", state="assembled", assembled_at=datetime.now(UTC), assembly_hash=HASH
        )
    with pytest.raises(IntegrityError, match="ck_binder_assembly"), db.begin_nested():
        new_binder(db, "ENG-C", assembled_at=datetime.now(UTC))  # open but timestamped
    new_binder(
        db,
        "ENG-D",
        report_date=REPORT_DATE,
        assembly_due=ASSEMBLY_DUE,
        retention_until=RETENTION_UNTIL,
        state="assembled",
        assembled_at=datetime.now(UTC),
        assembly_hash=HASH,
    )


def test_one_binder_per_engagement(db: Connection) -> None:
    name = unique("ENG")
    db.execute(insert(Binder).values(engagement=name, template="statutory"))
    with pytest.raises(IntegrityError, match="uq_binder_engagement"), db.begin_nested():
        db.execute(insert(Binder).values(engagement=name, template="statutory"))


# --- the migration itself ---------------------------------------------------------------------


@pytest.mark.skipif(
    not rebuild_allowed(),
    reason="destroys every row in oak_binder_test; opt in with OAK_TEST_REBUILD=yes",
)
def test_migration_downgrade_and_upgrade_again(test_database_url: str) -> None:
    cfg = alembic_config(test_database_url)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    engine = make_engine(test_database_url)
    try:
        assert {"binder", "wp", "wp_version", "wp_attachment"} <= set(
            inspect(engine).get_table_names()
        )
    finally:
        engine.dispose()
