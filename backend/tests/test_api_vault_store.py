"""The whole attachment path against the in-memory vault stand-in (D23): opaque document
ids, verified reads, duplicate references, and a purge that spares shared documents.
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
from tests.conftest import act_as, use_vault
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


def test_upload_and_download_through_a_vault_keep_id_and_hash_apart(api: TestClient) -> None:
    vault = use_vault(api)
    paper = create_paper(api, create_binder(api)["id"])
    (row,) = upload(api, paper["id"], "bank.pdf", PDF)["attachments"]
    assert row["sha256"] == sha256_of_bytes(PDF)
    assert row["vault_doc_id"].startswith("vault-") if "vault_doc_id" in row else True
    doc_ids = list(vault.documents)
    assert len(doc_ids) == 1 and doc_ids[0] != row["sha256"]
    assert vault.documents[doc_ids[0]][1:] == ("bank.pdf", "application/pdf")

    download = api.get(f"/api/attachments/{row['id']}/content")
    assert download.status_code == 200 and download.content == PDF
    assert download.headers["x-content-sha256"] == row["sha256"]


def test_a_vault_that_alters_a_document_is_caught_on_every_read(api: TestClient) -> None:
    vault = use_vault(api)
    binder = complete_binder(api)  # C-1 carries the CSV
    (doc_id,) = list(vault.documents)
    vault.tamper(doc_id, CSV + b"altered\n")

    detail = api.get(f"/api/binders/{binder['id']}").json()
    c1 = next(p for s in detail["sections"] for p in s["papers"] if p["ref"] == "C-1")
    (row,) = api.get(f"/api/papers/{c1['id']}").json()["attachments"]
    assert api.get(f"/api/attachments/{row['id']}/content").status_code == 409

    api.post(f"/api/binders/{binder['id']}/assemble").raise_for_status()
    report = api.get(f"/api/binders/{binder['id']}/verify").json()
    assert report["ok"] is False
    bad = next(c for c in report["checks"] if c["item"] == "attachment benchmark.csv")
    assert "no longer matches its hash" in bad["detail"]
    assert api.get(f"/api/binders/{binder['id']}/produce").status_code == 409


def test_produce_reads_native_bytes_from_the_vault(api: TestClient) -> None:
    use_vault(api)
    binder = complete_binder(api)
    api.post(f"/api/binders/{binder['id']}/assemble").raise_for_status()
    data = api.get(f"/api/binders/{binder['id']}/produce").content
    assert verify_archive(data) == []
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert archive.read("papers/C-1/attachments/benchmark.csv") == CSV


def test_identical_bytes_on_two_papers_share_one_vault_document(api: TestClient) -> None:
    vault = use_vault(api)
    binder_id = create_binder(api)["id"]
    first = create_paper(api, binder_id, ref="D-1")
    second = create_paper(api, binder_id, ref="D-2")
    (a,) = upload(api, first["id"], "a.csv", CSV)["attachments"]
    (b,) = upload(api, second["id"], "b.csv", CSV)["attachments"]
    assert a["sha256"] == b["sha256"]
    assert len(vault.documents) == 1  # stored once, referenced twice
    assert upload(api, first["id"], "again.csv", CSV, expected=409)


def test_purge_deletes_unshared_documents_and_spares_shared_ones(api: TestClient) -> None:
    vault = use_vault(api)
    # Two binders. The CSV is attached in both (complete_binder attaches it to C-1); the PDF
    # only in the first. Purging the first must delete the PDF and keep the CSV.
    first = complete_binder(api, report_date="2026-09-30")
    second = complete_binder(api, report_date="2026-09-30")
    first_detail = api.get(f"/api/binders/{first['id']}").json()
    x1 = next(p for s in first_detail["sections"] for p in s["papers"] if p["ref"] == "X-1")
    upload(api, x1["id"], "report.pdf", PDF)
    full_chain(api, x1["id"])
    assert len(vault.documents) == 2  # one CSV shared by both binders, one PDF
    for b in (first, second):
        api.post(f"/api/binders/{b['id']}/assemble").raise_for_status()

    cast(FastAPI, api.app).dependency_overrides[deps.today] = lambda: date(2033, 9, 30)
    act_as(api, PARTNER)
    purged = api.post(f"/api/binders/{first['id']}/purge")
    assert purged.status_code == 200, purged.text
    details = purged.json()["events"][-1]["details"]
    assert details["attachment_rows_deleted"] == 2
    assert details["documents_deleted"] == 1  # the PDF
    assert details["documents_retained_for_other_binders"] == 1  # the CSV
    assert len(vault.documents) == 1
    (remaining,) = vault.documents.values()
    assert remaining[0] == CSV

    # The second binder still reads its copy, and its own purge removes the last reference.
    second_detail = api.get(f"/api/binders/{second['id']}").json()
    c1 = next(p for s in second_detail["sections"] for p in s["papers"] if p["ref"] == "C-1")
    (row,) = api.get(f"/api/papers/{c1['id']}").json()["attachments"]
    assert api.get(f"/api/attachments/{row['id']}/content").content == CSV
    assert api.post(f"/api/binders/{second['id']}/purge").status_code == 200
    assert vault.documents == {}
