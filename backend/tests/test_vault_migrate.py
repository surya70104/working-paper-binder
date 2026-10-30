"""Moving local attachments into the Drive vault (D27): a dry run changes nothing; applying
uploads each document once, verifies it, rewrites the attachment rows and the
cross-references that name the document, keeps every hash and every local file, and skips
what is already in the vault. Against oak_binder_test; the test's own session is rolled
back."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Connection, select
from sqlalchemy.orm import Session

from oak_binder.hashing import sha256_of_bytes
from oak_binder.models import Binder, Wp, WpAttachment, Xref
from oak_binder.services.attachments import LocalAttachmentStore, verified_read
from oak_binder.vault_migrate import migrate
from tests.conftest import unique
from tests.fake_drive import FakeDrive

pytestmark = pytest.mark.db

PDF = b"%PDF-1.4 evidence\n"
CSV = b"a,b\n1,2\n"


def seed(session: Session, local: LocalAttachmentStore) -> tuple[Wp, Wp, str, str, set[uuid.UUID]]:
    binder = Binder(engagement=unique("ENG"), template="statutory", state="open")
    session.add(binder)
    session.flush()
    cash = Wp(binder_id=binder.id, ref="D-1", section="D", title="Cash")
    bank = Wp(binder_id=binder.id, ref="D-2", section="D", title="Bank")
    session.add_all([cash, bank])
    session.flush()
    pdf_key = local.put(PDF, filename="statement.pdf", media_type="application/pdf")
    csv_key = local.put(CSV, filename="tb.csv", media_type="text/csv")
    now = datetime.now(UTC)
    for paper, key, data, name, mime in (
        (cash, pdf_key, PDF, "statement.pdf", "application/pdf"),
        (bank, pdf_key, PDF, "statement-copy.pdf", "application/pdf"),  # shared document
        (bank, csv_key, CSV, "tb.csv", "text/csv"),
    ):
        session.add(
            WpAttachment(
                wp_id=paper.id,
                vault_doc_id=key,
                sha256=sha256_of_bytes(data),
                filename=name,
                media_type=mime,
                size_bytes=len(data),
                attached_by="preparer@firm",
                attached_at=now,
            )
        )
    session.add(
        Xref(
            from_wp=cash.id,
            to_vault_doc=csv_key,
            direction="to",
            created_by="preparer@firm",
            created_at=now,
        )
    )
    session.commit()  # a savepoint release under the test's rolled-back transaction
    return cash, bank, pdf_key, csv_key, {binder.id}


def test_dry_run_reports_and_changes_nothing(db: Connection, tmp_path: Path) -> None:
    session = Session(bind=db, join_transaction_mode="create_savepoint")
    local = LocalAttachmentStore(tmp_path / "local")
    cash, bank, _, _, scope = seed(session, local)
    drive = FakeDrive()
    report = migrate(session, local, drive.store(), apply=False, binder_ids=scope)
    assert report.documents_found == 2 and report.documents_moved == 0
    assert report.rows_rewritten == 0 and report.problems == []
    assert drive.vault_files() == {}
    # The seeded rows still carry local keys; rows of other binders in the shared test
    # database (the migrated demo attachment) are not this test's concern.
    seeded = session.scalars(
        select(WpAttachment).where(WpAttachment.wp_id.in_([cash.id, bank.id]))
    ).all()
    assert len(seeded) == 3 and all(len(r.vault_doc_id) == 64 for r in seeded)
    assert "DRY RUN" in report.lines()[0]


def test_apply_moves_each_document_once_and_rewrites_every_reference(
    db: Connection, tmp_path: Path
) -> None:
    session = Session(bind=db, join_transaction_mode="create_savepoint")
    local = LocalAttachmentStore(tmp_path / "local")
    cash, bank, pdf_key, csv_key, scope = seed(session, local)
    drive = FakeDrive()
    store = drive.store()

    report = migrate(session, local, store, apply=True, binder_ids=scope)
    assert report.problems == []
    assert report.documents_found == 2 and report.documents_moved == 2
    assert report.rows_rewritten == 3 and report.xrefs_rewritten == 1
    assert len(drive.vault_files()) == 2  # the shared PDF went up once

    rows = session.scalars(
        select(WpAttachment).where(WpAttachment.wp_id.in_([cash.id, bank.id]))
    ).all()
    assert {r.vault_doc_id[:6] for r in rows} == {"drive-"}
    shared = {r.vault_doc_id for r in rows if r.sha256 == sha256_of_bytes(PDF)}
    assert len(shared) == 1  # both rows name the same Drive file
    for row in rows:
        assert row.sha256 == sha256_of_bytes(PDF if row.media_type == "application/pdf" else CSV)
        assert verified_read(store, row) in (PDF, CSV)  # the hash still holds through Drive
    (xref,) = session.scalars(select(Xref).where(Xref.from_wp == cash.id)).all()
    assert xref.to_vault_doc == next(r.vault_doc_id for r in rows if r.media_type == "text/csv")
    # The local copies stay.
    assert local.read(pdf_key) == PDF and local.read(csv_key) == CSV
    assert drive.list_calls() == [] and drive.touched_outside_vault() == []

    again = migrate(session, local, store, apply=True, binder_ids=scope)
    assert again.documents_found == 0 and again.already_in_vault == 3


def test_a_local_file_that_does_not_match_its_hash_is_not_moved(
    db: Connection, tmp_path: Path
) -> None:
    session = Session(bind=db, join_transaction_mode="create_savepoint")
    local = LocalAttachmentStore(tmp_path / "local")
    _, _, pdf_key, _, scope = seed(session, local)
    local.path_for(pdf_key).write_bytes(b"%PDF tampered")
    drive = FakeDrive()
    report = migrate(session, local, drive.store(), apply=True, binder_ids=scope)
    assert report.documents_moved == 1  # the CSV
    assert any("do not match the recorded hash" in p for p in report.problems)
    pdf_rows = session.scalars(
        select(WpAttachment).where(WpAttachment.vault_doc_id == pdf_key)
    ).all()
    assert len(pdf_rows) == 2  # untouched, still local keys


def test_a_drive_failure_leaves_the_rows_as_they_were(db: Connection, tmp_path: Path) -> None:
    session = Session(bind=db, join_transaction_mode="create_savepoint")
    local = LocalAttachmentStore(tmp_path / "local")
    *_, scope = seed(session, local)
    drive = FakeDrive()
    drive.fail_with = 503
    report = migrate(session, local, drive.store(), apply=True, binder_ids=scope)
    assert report.documents_moved == 0 and len(report.problems) == 2
    assert all("Google Drive" in p and "fake-" not in p for p in report.problems)
