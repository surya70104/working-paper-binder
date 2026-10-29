"""Service-level rules that the API cannot reach, against oak_binder_test: the content-drift
check at review and the version-number race."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import Connection
from sqlalchemy.orm import Session, sessionmaker

from oak_binder.errors import Conflict
from oak_binder.models import Wp, WpStatus
from oak_binder.services import binders, papers
from tests.conftest import unique

pytestmark = pytest.mark.db


@pytest.fixture
def session(db: Connection) -> Iterator[Session]:
    """A session on the rolled-back test connection; commits become savepoint releases."""
    factory = sessionmaker(bind=db, join_transaction_mode="create_savepoint")
    with factory() as s:
        yield s


def paper_in_review(session: Session) -> Wp:
    binder = binders.create_binder(
        session, engagement=unique("ENG"), template="statutory", report_date=None
    )
    paper = papers.create_paper(
        session,
        binder,
        {"ref": "D-1", "section": "D", "title": "Cash", "conclusion": "Fairly stated"},
    )
    papers.prepare(session, paper, "preparer@firm", datetime.now(UTC))
    papers.submit_for_review(session, paper)
    return paper


def test_review_refuses_content_that_drifted_from_the_prepared_version(session: Session) -> None:
    # Through the API an edit returns the paper to draft, so review can never see drift.
    # The service still checks the hash so the invariant does not depend on that rule.
    paper = paper_in_review(session)
    paper.title = "Cash and bank"  # direct change, bypassing update_paper
    session.flush()
    with pytest.raises(Conflict, match="changed since version 1 was prepared"):
        papers.review(session, paper, "reviewer@firm", datetime.now(UTC))
    assert paper.status == WpStatus.IN_REVIEW
    assert [v.version for v in papers.versions(session, paper)] == [1]


def test_sign_off_refuses_content_that_drifted_from_the_reviewed_version(
    session: Session,
) -> None:
    paper = paper_in_review(session)
    papers.review(session, paper, "reviewer@firm", datetime.now(UTC))
    paper.conclusion = "Fairly stated, revised"
    session.flush()
    with pytest.raises(Conflict, match="changed since version 2 was reviewed"):
        papers.sign_off(session, paper, "partner@firm", datetime.now(UTC))


def test_concurrent_sign_offs_collide_as_a_conflict_not_a_server_error(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Two requests computing the same next version number: the second insert violates
    # uq_wp_version_wp_version and must surface as 409, not 500.
    paper = paper_in_review(session)
    monkeypatch.setattr(papers, "next_version_number", lambda session, paper: 1)
    with pytest.raises(Conflict, match="another request at the same time"):
        papers.review(session, paper, "reviewer@firm", datetime.now(UTC))
