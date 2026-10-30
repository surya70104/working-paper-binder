"""Attachments over the API against oak_binder_test (spec 3B, 3G; D7, D17): native bytes,
SHA-256, a store outside the web root, hash-checked reads, and the join with versions."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from oak_binder.hashing import sha256_of_bytes
from tests.helpers import CSV, PDF, create_binder, create_paper, full_chain, step, upload

pytestmark = pytest.mark.db


def store_root(api: TestClient) -> Path:
    root: Path = cast(FastAPI, api.app).state.attachment_store.root
    return root


def test_upload_preserves_bytes_and_records_the_hash(api: TestClient) -> None:
    paper = create_paper(api, create_binder(api)["id"])
    result = upload(
        api, paper["id"], "bank confirmation.pdf", PDF, identifying_chars="HDFC a/c 1234"
    )
    (attachment,) = result["attachments"]
    assert attachment["sha256"] == sha256_of_bytes(PDF)
    assert attachment["filename"] == "bank confirmation.pdf"
    assert attachment["media_type"] == "application/pdf"
    assert attachment["size_bytes"] == len(PDF)
    assert attachment["identifying_chars"] == "HDFC a/c 1234"
    assert attachment["attached_by"] == "preparer@firm" and attachment["attached_at"]
    assert attachment["wp_version_id"] is None  # not yet part of any signed version

    download = api.get(f"/api/attachments/{attachment['id']}/content")
    assert download.status_code == 200
    assert download.content == PDF  # byte for byte, native format
    assert download.headers["content-type"].startswith("application/pdf")
    assert 'filename="bank confirmation.pdf"' in download.headers["content-disposition"]
    assert download.headers["x-content-sha256"] == attachment["sha256"]
    assert download.headers["x-content-type-options"] == "nosniff"


def test_downloads_never_let_the_browser_sniff_a_type(api: TestClient) -> None:
    # A text file whose bytes look like HTML must still be served as text/plain and marked
    # nosniff, so a browser never renders an upload as a page.
    paper = create_paper(api, create_binder(api)["id"])
    html_bytes = b"<html><script>alert(1)</script></html>"
    (attachment,) = upload(api, paper["id"], "notes.txt", html_bytes)["attachments"]
    download = api.get(f"/api/attachments/{attachment['id']}/content")
    assert download.status_code == 200
    assert download.content == html_bytes  # bytes are never altered
    assert download.headers["content-type"].startswith("text/plain")
    assert download.headers["x-content-type-options"] == "nosniff"
    assert download.headers["content-disposition"].startswith("attachment;")


def test_files_live_under_the_store_by_hash_outside_any_served_folder(api: TestClient) -> None:
    paper = create_paper(api, create_binder(api)["id"])
    (attachment,) = upload(api, paper["id"], "x.pdf", PDF)["attachments"]
    root = store_root(api)
    expected = root / attachment["sha256"][:2] / attachment["sha256"]
    assert expected.is_file() and expected.read_bytes() == PDF
    assert root.is_relative_to(Path(__file__).resolve().parents[1]) is False  # not in backend/
    assert "frontend" not in root.parts and "dist" not in root.parts


def test_same_bytes_are_stored_once_and_refused_twice_on_one_paper(api: TestClient) -> None:
    binder_id = create_binder(api)["id"]
    first = create_paper(api, binder_id, ref="D-1")
    second = create_paper(api, binder_id, ref="D-2")
    upload(api, first["id"], "a.csv", CSV)
    upload(api, second["id"], "b.csv", CSV)  # another paper may hold the same evidence
    files = [p for p in store_root(api).rglob("*") if p.is_file()]
    assert len(files) == 1
    duplicate = upload(api, first["id"], "a-again.csv", CSV, expected=409)
    assert "already attached" in duplicate["detail"]


def test_upload_validation(api: TestClient) -> None:
    paper = create_paper(api, create_binder(api)["id"])
    assert "not an accepted" in upload(api, paper["id"], "macro.xlsm", PDF, expected=415)["detail"]
    assert "not an accepted" in upload(api, paper["id"], "noext", PDF, expected=415)["detail"]
    assert "empty" in upload(api, paper["id"], "empty.pdf", b"", expected=422)["detail"]
    too_big = b"x" * (64 * 1024 + 1)
    assert (
        "exceeds the limit" in upload(api, paper["id"], "big.csv", too_big, expected=413)["detail"]
    )


def test_attaching_is_a_content_change_and_joins_the_next_signed_version(api: TestClient) -> None:
    paper = create_paper(api, create_binder(api)["id"])
    step(api, paper["id"], "prepare")
    with_file = upload(api, paper["id"], "evidence.csv", CSV)
    assert with_file["status"] == "draft"  # the prepared version did not cover this file
    assert with_file["versions"][0]["body"]["attachments"] == []

    signed = full_chain(api, paper["id"])
    (attachment,) = signed["attachments"]
    prepared_again = signed["versions"][1]
    assert attachment["wp_version_id"] is not None
    assert prepared_again["body"]["attachments"] == [
        {
            "sha256": sha256_of_bytes(CSV),
            "filename": "evidence.csv",
            "size_bytes": len(CSV),
            "identifying_chars": None,
        }
    ]
    assert prepared_again["content_hash"] != signed["versions"][0]["content_hash"]


def test_remove_before_assembly_returns_the_paper_to_draft(api: TestClient) -> None:
    paper = create_paper(api, create_binder(api)["id"])
    (attachment,) = upload(api, paper["id"], "a.csv", CSV)["attachments"]
    step(api, paper["id"], "prepare")
    removed = api.delete(f"/api/attachments/{attachment['id']}")
    assert removed.status_code == 204
    after = api.get(f"/api/papers/{paper['id']}").json()
    assert after["attachments"] == [] and after["status"] == "draft"
    assert after["versions"][0]["body"]["attachments"][0]["sha256"] == attachment["sha256"]
    assert api.get(f"/api/attachments/{attachment['id']}").status_code == 404


def test_a_tampered_stored_file_is_refused_not_served(api: TestClient) -> None:
    paper = create_paper(api, create_binder(api)["id"])
    (attachment,) = upload(api, paper["id"], "a.csv", CSV)["attachments"]
    path = store_root(api) / attachment["sha256"][:2] / attachment["sha256"]
    path.write_bytes(CSV.replace(b"100000", b"900000"))
    refused = api.get(f"/api/attachments/{attachment['id']}/content")
    assert refused.status_code == 409
    assert "no longer matches its hash" in refused.json()["detail"]
    path.unlink()
    missing = api.get(f"/api/attachments/{attachment['id']}/content")
    assert missing.status_code == 404
