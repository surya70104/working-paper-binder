"""Database rules added by migration 0009, against oak_binder_test: wp_review is append-only,
one review per level per version, non-blank level and reviewer; a binder's review levels
cannot change once a level review exists for one of its papers; the application role can
only read and insert reviews."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import Connection, delete, insert, select, text, update
from sqlalchemy.exc import IntegrityError, ProgrammingError

from oak_binder.models import Binder, Wp, WpReview, WpVersion
from tests.conftest import unique

pytestmark = pytest.mark.db


def binder(db: Connection, levels: list[str] | None = None) -> uuid.UUID:
    result: uuid.UUID = db.execute(
        insert(Binder)
        .values(engagement=unique("ENG"), template="statutory", review_levels=levels)
        .returning(Binder.id)
    ).scalar_one()
    return result


def prepared_version(
    db: Connection, binder_id: uuid.UUID, ref: str = "D-1"
) -> tuple[uuid.UUID, uuid.UUID]:
    wp_id: uuid.UUID = db.execute(
        insert(Wp)
        .values(binder_id=binder_id, ref=ref, section="D", title=f"Paper {ref}")
        .returning(Wp.id)
    ).scalar_one()
    version_id: uuid.UUID = db.execute(
        insert(WpVersion)
        .values(
            wp_id=wp_id,
            version=1,
            body={"title": f"Paper {ref}"},
            prepared_by="preparer@firm",
            prepared_at=datetime.now(UTC),
            content_hash="a" * 64,
        )
        .returning(WpVersion.id)
    ).scalar_one()
    return wp_id, version_id


def review(db: Connection, wp_id: uuid.UUID, version_id: uuid.UUID, **extra: Any) -> uuid.UUID:
    values: dict[str, Any] = {
        "wp_id": wp_id,
        "wp_version_id": version_id,
        "level": "senior",
        "reviewer": "senior@firm",
        "reviewed_at": datetime.now(UTC),
    }
    values.update(extra)
    result: uuid.UUID = db.execute(
        insert(WpReview).values(**values).returning(WpReview.id)
    ).scalar_one()
    return result


def test_level_reviews_are_append_only(db: Connection) -> None:
    wp_id, version_id = prepared_version(db, binder(db, ["senior", "partner"]))
    row_id = review(db, wp_id, version_id)
    with pytest.raises(IntegrityError, match="wp_review is append-only: UPDATE"), db.begin_nested():
        db.execute(update(WpReview).where(WpReview.id == row_id).values(reviewer="other@firm"))
    with pytest.raises(IntegrityError, match="wp_review is append-only: DELETE"), db.begin_nested():
        db.execute(delete(WpReview).where(WpReview.id == row_id))
    with (
        pytest.raises(IntegrityError, match="wp_review is append-only: TRUNCATE"),
        db.begin_nested(),
    ):
        db.execute(text("TRUNCATE wp_review"))
    assert (
        db.execute(select(WpReview.reviewer).where(WpReview.id == row_id)).scalar_one()
        == "senior@firm"
    )


def test_one_review_per_level_per_version_and_no_blanks(db: Connection) -> None:
    wp_id, version_id = prepared_version(db, binder(db, ["senior", "partner"]))
    review(db, wp_id, version_id, level="senior")
    with pytest.raises(IntegrityError, match="uq_wp_review_version_level"), db.begin_nested():
        review(db, wp_id, version_id, level="senior", reviewer="another@firm")
    review(db, wp_id, version_id, level="partner")  # another level of the same version is fine
    with pytest.raises(IntegrityError, match="ck_wp_review_level_not_blank"), db.begin_nested():
        review(db, wp_id, version_id, level="  ")
    with pytest.raises(IntegrityError, match="ck_wp_review_reviewer_not_blank"), db.begin_nested():
        review(db, wp_id, version_id, level="manager", reviewer="")
    with pytest.raises(IntegrityError, match="fk_wp_review_wp_version"), db.begin_nested():
        review(db, wp_id, uuid.uuid4())


def test_review_levels_freeze_at_the_database_once_a_level_review_exists(db: Connection) -> None:
    binder_id = binder(db, ["senior", "manager", "partner"])
    # Before any review the configuration moves freely.
    db.execute(
        update(Binder).where(Binder.id == binder_id).values(review_levels=["senior", "partner"])
    )
    wp_id, version_id = prepared_version(db, binder_id)
    review(db, wp_id, version_id, level="senior")
    with pytest.raises(IntegrityError, match="review levels are frozen"), db.begin_nested():
        db.execute(update(Binder).where(Binder.id == binder_id).values(review_levels=["senior"]))
    with pytest.raises(IntegrityError, match="review levels are frozen"), db.begin_nested():
        db.execute(update(Binder).where(Binder.id == binder_id).values(review_levels=None))
    # Other columns of the binder still change; the same value is not a change.
    db.execute(
        update(Binder).where(Binder.id == binder_id).values(review_levels=["senior", "partner"])
    )
    db.execute(update(Binder).where(Binder.id == binder_id).values(engagement=unique("ENG")))
    assert db.execute(select(Binder.review_levels).where(Binder.id == binder_id)).scalar_one() == [
        "senior",
        "partner",
    ]
    # Another binder with no reviews is unaffected.
    other = binder(db, ["senior"])
    db.execute(update(Binder).where(Binder.id == other).values(review_levels=["manager"]))


def test_an_empty_level_list_is_refused(db: Connection) -> None:
    with (
        pytest.raises(IntegrityError, match="ck_binder_review_levels_not_empty"),
        db.begin_nested(),
    ):
        binder(db, [])
    binder(db, None)  # not configured: the Pass 1 chain


def test_application_role_cannot_rewrite_reviews(app_db: Connection) -> None:
    for statement in (
        "UPDATE wp_review SET level = 'x' WHERE false",
        "DELETE FROM wp_review WHERE false",
    ):
        with pytest.raises(ProgrammingError, match="permission denied"), app_db.begin_nested():
            app_db.execute(text(statement))
    app_db.execute(text("SELECT count(*) FROM wp_review")).scalar_one()
