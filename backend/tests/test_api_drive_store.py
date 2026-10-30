"""The whole attachment path through the Google Drive adapter and its double (D27): upload,
download with the hash re-checked, assembly and verification, production from Drive bytes,
purge that deletes only this binder's documents, and confinement to the vault folder.
Against oak_binder_test; every test rolls back."""

from __future__ import annotations

import io
import zipfile
from datetime import date
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from oak_binder.api import deps
from oak_binder.hashing import sha256_of_bytes
from oak_binder.services.produce import verify_archive
from tests.conftest import act_as
from tests.fake_drive import FOLDER_ID, FakeDrive
from tests.helpers import (
    CSV,
    PARTNER,
    PDF,
    complete_binder,
    create_binder,
    create_paper,
    full_chain,
    upload,
)

pytestmark = pytest.mark.db


def use_drive(api: TestClient) -> FakeDrive:
    drive = FakeDrive()
    cast(FastAPI, api.app).state.attachment_store = drive.store()
    return drive


def test_upload_lands_in_the_vault_folder_and_downloads_verified(api: TestClient) -> None:
    drive = use_drive(api)
    paper = create_paper(api, create_binder(api)["id"])
    (row,) = upload(api, paper["id"], "bank.pdf", PDF)["attachments"]
    assert row["sha256"] == sha256_of_bytes(PDF)
    assert row["vault_doc_id"].startswith("drive-") and row["vault_doc_id"] != row["sha256"]
    stored = drive.files[row["vault_doc_id"]]
    assert stored.parents == [FOLDER_ID] and stored.read_only and stored.name == "bank.pdf"
    download = api.get(f"/api/attachments/{row['id']}/content")
    assert download.status_code == 200 and download.content == PDF
    assert download.headers["x-content-sha256"] == row["sha256"]
    assert drive.list_calls() == [] and drive.touched_outside_vault() == []


def test_a_document_altered_in_drive_is_caught_on_download_verify_and_produce(
    api: TestClient,
) -> None:
    drive = use_drive(api)
    binder = complete_binder(api)  # C-1 carries the CSV
    (doc_id,) = list(drive.vault_files())
    drive.tamper(doc_id, CSV + b"altered\n")
    detail = api.get(f"/api/binders/{binder['id']}").json()
    c1 = next(p for s in detail["sections"] for p in s["papers"] if p["ref"] == "C-1")
    (row,) = api.get(f"/api/papers/{c1['id']}").json()["attachments"]
    assert api.get(f"/api/attachments/{row['id']}/content").status_code == 409
    act_as(api, PARTNER)
    api.post(f"/api/binders/{binder['id']}/assemble").raise_for_status()
    report = api.get(f"/api/binders/{binder['id']}/verify").json()
    assert report["ok"] is False
    assert api.get(f"/api/binders/{binder['id']}/produce").status_code == 409


def test_a_document_trashed_in_drive_fails_verification_by_name(api: TestClient) -> None:
    drive = use_drive(api)
    binder = complete_binder(api)
    act_as(api, PARTNER)
    api.post(f"/api/binders/{binder['id']}/assemble").raise_for_status()
    (doc_id,) = list(drive.vault_files())
    drive.trash(doc_id)
    report = api.get(f"/api/binders/{binder['id']}/verify").json()
    bad = next(c for c in report["checks"] if c["item"] == "attachment benchmark.csv")
    assert bad["ok"] is False and "missing from the Drive vault folder" in bad["detail"]


def test_produce_reads_native_bytes_from_drive(api: TestClient) -> None:
    use_drive(api)
    binder = complete_binder(api)
    act_as(api, PARTNER)
    api.post(f"/api/binders/{binder['id']}/assemble").raise_for_status()
    produced = api.get(f"/api/binders/{binder['id']}/produce")
    assert produced.status_code == 200
    assert verify_archive(produced.content) == []
    with zipfile.ZipFile(io.BytesIO(produced.content)) as archive:
        assert archive.read("papers/C-1/attachments/benchmark.csv") == CSV


def test_identical_bytes_on_two_papers_are_one_drive_file(api: TestClient) -> None:
    drive = use_drive(api)
    binder_id = create_binder(api)["id"]
    first = create_paper(api, binder_id, ref="D-1")
    second = create_paper(api, binder_id, ref="D-2")
    (a,) = upload(api, first["id"], "a.csv", CSV)["attachments"]
    (b,) = upload(api, second["id"], "b.csv", CSV)["attachments"]
    assert a["vault_doc_id"] == b["vault_doc_id"]
    assert len(drive.vault_files()) == 1


def test_purge_deletes_this_binders_documents_only_and_nothing_else_in_drive(
    api: TestClient,
) -> None:
    drive = use_drive(api)
    first = complete_binder(api, report_date="2026-09-30")
    second = complete_binder(api, report_date="2026-09-30")
    detail = api.get(f"/api/binders/{first['id']}").json()
    x1 = next(p for s in detail["sections"] for p in s["papers"] if p["ref"] == "X-1")
    upload(api, x1["id"], "report.pdf", PDF)
    full_chain(api, x1["id"])
    act_as(api, PARTNER)
    for b in (first, second):
        api.post(f"/api/binders/{b['id']}/assemble").raise_for_status()
    assert len(drive.vault_files()) == 2  # the shared CSV and the PDF

    cast(FastAPI, api.app).dependency_overrides[deps.today] = lambda: date(2033, 9, 30)
    try:
        purged = api.post(f"/api/binders/{first['id']}/purge")
        assert purged.status_code == 200, purged.text
        details = purged.json()["events"][-1]["details"]
        assert details["documents_deleted"] == 1
        assert details["documents_retained_for_other_binders"] == 1
        assert len(drive.vault_files()) == 1
        (remaining,) = drive.vault_files().values()
        assert remaining.data == CSV
        assert "outside-1" in drive.files and drive.touched_outside_vault() == []
        assert api.post(f"/api/binders/{second['id']}/purge").status_code == 200
        assert drive.vault_files() == {}
        assert drive.list_calls() == []
    finally:
        cast(FastAPI, api.app).dependency_overrides.pop(deps.today, None)


def test_a_drive_outage_is_a_503_and_nothing_is_half_written(api: TestClient) -> None:
    drive = use_drive(api)
    paper = create_paper(api, create_binder(api)["id"])
    drive.fail_with = 503
    response = api.post(
        f"/api/papers/{paper['id']}/attachments",
        files={"file": ("a.pdf", PDF, "application/octet-stream")},
    )
    assert response.status_code == 503
    assert "Google Drive could not" in response.json()["detail"]
    assert "fake-" not in response.text
    drive.fail_with = None
    assert api.get(f"/api/papers/{paper['id']}").json()["attachments"] == []
