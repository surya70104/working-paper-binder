"""The access log over the API (spec 3H, 4; D25): every read of an assembled or purged file
is recorded with who and what; reads of an open binder are not; a read of an assembled file
without an identity is refused rather than logged anonymously."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import date
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from oak_binder.api import deps
from tests.conftest import PREPARER, act_as
from tests.helpers import PARTNER, complete_binder, create_binder, create_paper

pytestmark = pytest.mark.db

AUDITOR = "quality.reviewer@firm"


def access_of(api: TestClient, binder_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = api.get(f"/api/binders/{binder_id}/assembly").json()["access"]
    return rows


def assembled_binder(api: TestClient) -> dict[str, Any]:
    binder = complete_binder(api)
    act_as(api, PARTNER)
    assert api.post(f"/api/binders/{binder['id']}/assemble").status_code == 200
    return binder


def test_reads_of_an_open_binder_are_not_logged_and_need_no_identity(api: TestClient) -> None:
    binder = create_binder(api)
    paper = create_paper(api, binder["id"])
    act_as(api, None)  # no identity configured at all
    assert api.get(f"/api/binders/{binder['id']}").status_code == 200
    assert api.get(f"/api/papers/{paper['id']}").status_code == 200
    assert api.get(f"/api/binders/{binder['id']}/assembly").status_code == 200
    act_as(api, PREPARER)
    assert access_of(api, binder["id"]) == []


def test_every_read_of_an_assembled_file_is_logged_with_who_and_what(api: TestClient) -> None:
    binder = assembled_binder(api)
    paper = next(p for s in binder["sections"] for p in s["papers"] if p["ref"] == "C-1")
    detail = api.get(f"/api/papers/{paper['id']}").json()
    attachment = detail["attachments"][0]

    act_as(api, AUDITOR)
    assert api.get(f"/api/binders/{binder['id']}").status_code == 200
    assert api.get(f"/api/papers/{paper['id']}").status_code == 200
    assert api.get(f"/api/attachments/{attachment['id']}/content").status_code == 200
    assert api.get(f"/api/binders/{binder['id']}/verify").status_code == 200
    produced = api.get(f"/api/binders/{binder['id']}/produce")
    assert produced.status_code == 200

    rows = access_of(api, binder["id"])
    by_auditor = [(r["action"], r["at"]) for r in rows if r["user"] == AUDITOR]
    actions = [a for a, _ in by_auditor]
    assert actions == [
        "binder",
        "paper C-1",
        "attachment benchmark.csv of C-1",
        "verify",
        "produce",
        "assembly status",  # the read that listed the log is itself logged
    ]
    assert [at for _, at in by_auditor] == sorted(at for _, at in by_auditor)
    # Assembling itself is an action, not a read; the only other row is the partner's read of
    # the paper (to find the attachment) after assembly, before the auditor came in.
    assert [(r["user"], r["action"]) for r in rows if r["user"] != AUDITOR] == [
        (PARTNER, "paper C-1")
    ]
    assert all(r["user"] and r["action"] and r["at"] for r in rows)

    # The produced archive carries the log as it stood at production, and in the trail.
    with zipfile.ZipFile(io.BytesIO(produced.content)) as archive:
        log = json.loads(archive.read("access_log.json"))
        assert [e["action"] for e in log if e["user"] == AUDITOR] == [
            "binder",
            "paper C-1",
            "attachment benchmark.csv of C-1",
            "verify",
        ]
        trail = json.loads(archive.read("audit_trail.json"))
        access_entries = [e for e in trail if e["kind"] == "access"]
        assert {e["actor"] for e in access_entries} == {PARTNER, AUDITOR}
        assert access_entries[-1]["details"] == {"action": "verify"}
        checksums = archive.read("CHECKSUMS.sha256").decode()
        assert "  access_log.json\n" in checksums


def test_every_other_read_of_an_assembled_file_is_logged_too(api: TestClient) -> None:
    binder = assembled_binder(api)
    paper = next(p for s in binder["sections"] for p in s["papers"] if p["ref"] == "C-1")
    attachment = api.get(f"/api/papers/{paper['id']}").json()["attachments"][0]
    note = api.post(f"/api/papers/{paper['id']}/review-notes", json={"text": "Tie out"}).json()

    act_as(api, AUDITOR)
    assert api.get(f"/api/papers/{paper['id']}/versions").status_code == 200
    assert api.get(f"/api/papers/{paper['id']}/review-notes").status_code == 200
    assert api.get(f"/api/review-notes/{note['note_id']}").status_code == 200
    assert api.get(f"/api/papers/{paper['id']}/xrefs").status_code == 200
    assert api.get(f"/api/attachments/{attachment['id']}").status_code == 200
    assert api.get(f"/api/binders/{binder['id']}/review-notes").status_code == 200
    actions = [r["action"] for r in access_of(api, binder["id"]) if r["user"] == AUDITOR]
    assert actions == [
        "versions of C-1",
        "review notes of C-1",
        "review note of C-1",
        "cross-references of C-1",
        "attachment benchmark.csv of C-1 (details)",
        "review notes",
        "assembly status",
    ]
    # And none of them is served anonymously.
    act_as(api, None)
    for path in (
        f"/api/papers/{paper['id']}/versions",
        f"/api/papers/{paper['id']}/review-notes",
        f"/api/review-notes/{note['note_id']}",
        f"/api/papers/{paper['id']}/xrefs",
        f"/api/attachments/{attachment['id']}",
        f"/api/attachments/{attachment['id']}/content",
        f"/api/binders/{binder['id']}/review-notes",
    ):
        assert api.get(path).status_code == 503, path


def test_reading_an_assembled_file_without_an_identity_is_refused(api: TestClient) -> None:
    binder = assembled_binder(api)
    paper = next(p for s in binder["sections"] for p in s["papers"] if p["ref"] == "C-1")
    before = access_of(api, binder["id"])

    act_as(api, None)
    for path in (
        f"/api/binders/{binder['id']}",
        f"/api/papers/{paper['id']}",
        f"/api/binders/{binder['id']}/assembly",
        f"/api/binders/{binder['id']}/verify",
    ):
        refused = api.get(path)
        assert refused.status_code == 503, path
        assert "No identity is configured" in refused.json()["detail"]

    act_as(api, PARTNER)
    after = access_of(api, binder["id"])
    assert after[:-1] == before  # nothing anonymous was written; only this last read is new
    assert after[-1]["user"] == PARTNER


def test_header_mode_logs_the_proxy_identity_and_refuses_without_it(api: TestClient) -> None:
    binder = assembled_binder(api)
    settings = cast(FastAPI, api.app).state.settings
    settings.auth = "header"
    settings.dev_user = None
    try:
        anonymous = api.get(f"/api/binders/{binder['id']}")
        assert anonymous.status_code == 401
        assert "did not present X-Authenticated-User" in anonymous.json()["detail"]
        named = api.get(
            f"/api/binders/{binder['id']}", headers={"X-Authenticated-User": "  nfra.inspector  "}
        )
        assert named.status_code == 200
        rows = api.get(
            f"/api/binders/{binder['id']}/assembly", headers={"X-Authenticated-User": PARTNER}
        ).json()["access"]
        assert [r["user"] for r in rows] == ["nfra.inspector", PARTNER]
    finally:
        settings.auth = "dev"
        settings.dev_user = PREPARER


def test_reads_of_a_purged_file_are_still_logged(api: TestClient) -> None:
    binder = assembled_binder(api)
    cast(FastAPI, api.app).dependency_overrides[deps.today] = lambda: date(2033, 10, 1)
    try:
        act_as(api, PARTNER)
        assert api.post(f"/api/binders/{binder['id']}/purge").status_code == 200
        act_as(api, AUDITOR)
        assert api.get(f"/api/binders/{binder['id']}").json()["state"] == "purged"
        rows = access_of(api, binder["id"])
        assert [r["action"] for r in rows if r["user"] == AUDITOR] == ["binder", "assembly status"]
    finally:
        cast(FastAPI, api.app).dependency_overrides.pop(deps.today, None)
