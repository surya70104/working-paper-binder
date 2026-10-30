"""Assembly, amendment, verification, produce-file and purge over the API against
oak_binder_test (spec 3F, 3G, 8.3 to 8.7)."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import date
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from oak_binder.api import deps
from oak_binder.hashing import content_hash, sha256_of_bytes
from oak_binder.services.produce import verify_archive
from tests.conftest import act_as
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


def assembly(api: TestClient, binder_id: str) -> dict[str, Any]:
    result: dict[str, Any] = api.get(f"/api/binders/{binder_id}/assembly").json()
    return result


def pretend_today(api: TestClient, day: date) -> None:
    cast(FastAPI, api.app).dependency_overrides[deps.today] = lambda: day


# --- 8.3: blockers, each named ----------------------------------------------------------------


def test_assembly_is_blocked_by_named_items(api: TestClient) -> None:
    binder = create_binder(api)  # undated, nothing filed
    paper = create_paper(api, binder["id"], ref="C-1", section="C", title="Materiality memo")
    status = assembly(api, binder["id"])
    kinds = {(b["kind"], b["ref"]) for b in status["blockers"]}
    assert ("report_not_dated", None) in kinds
    for ref in ("A-1", "B-1", "W-1", "X-1", "Z-1"):
        assert ("missing_required_paper", ref) in kinds
    assert ("missing_required_paper", "C-1") not in kinds  # it exists, but is unsigned
    assert ("unsigned_paper", "C-1") in kinds
    assert any("Pass 2" in n for n in status["not_checked"])
    assert len(status["not_checked"]) == 1  # broken cross-references; notes are now checked

    refused = api.post(f"/api/binders/{binder['id']}/assemble")
    assert refused.status_code == 409
    detail = refused.json()["detail"]
    assert "blocked by 7 item(s)" in detail
    assert "missing_required_paper A-1" in detail and "unsigned_paper C-1" in detail
    assert "report_not_dated" in detail
    assert api.get(f"/api/binders/{binder['id']}").json()["state"] == "open"

    full_chain(api, paper["id"])
    assert ("unsigned_paper", "C-1") not in {
        (b["kind"], b["ref"]) for b in assembly(api, binder["id"])["blockers"]
    }


# --- 3F, 8.5: assemble, manifest, reproducible hash -------------------------------------------


def test_assemble_freezes_the_file_with_a_manifest_and_hash(api: TestClient) -> None:
    binder = complete_binder(api)
    assert assembly(api, binder["id"])["blockers"] == []
    act_as(api, PARTNER)
    done = api.post(f"/api/binders/{binder['id']}/assemble")
    assert done.status_code == 200, done.text
    status = done.json()
    assert status["state"] == "assembled"
    assert status["assembled_at"]
    assert len(status["assembly_hash"]) == 64

    manifest = status["manifest"]
    refs = [p["ref"] for p in manifest["papers"]]
    assert refs == sorted(refs) == ["A-1", "B-1", "C-1", "W-1", "X-1", "Z-1"]
    for entry in manifest["papers"]:
        paper = api.get(f"/api/papers/{entry['wp_id']}").json()
        assert entry["status"] == "signed_off"
        assert entry["version"] == paper["current_version"]
        assert entry["content_hash"] == paper["versions"][-1]["content_hash"]
    c1 = next(p for p in manifest["papers"] if p["ref"] == "C-1")
    assert c1["attachments"][0]["sha256"] == sha256_of_bytes(CSV)
    assert c1["attachments"][0]["identifying_chars"] == "FY26 TB rows 1-2"

    # Spec 8.5: re-computing the file hash from the manifest reproduces it.
    assert content_hash(manifest) == status["assembly_hash"]
    (event,) = status["events"]
    assert event["kind"] == "assembled" and event["actor"] == PARTNER
    assert event["details"]["file_hash"] == status["assembly_hash"]
    assert event["details"]["previous_file_hash"] is None

    again = api.post(f"/api/binders/{binder['id']}/assemble")
    assert again.status_code == 409 and "nothing has changed" in again.json()["detail"]


def test_verify_reproduces_every_hash_and_detects_tampering(api: TestClient) -> None:
    binder = complete_binder(api)
    api.post(f"/api/binders/{binder['id']}/assemble").raise_for_status()
    report = api.get(f"/api/binders/{binder['id']}/verify").json()
    assert report["ok"] is True
    assert report["recomputed_from_recorded_manifest"] == report["assembly_hash"]
    assert report["current_file_hash"] == report["assembly_hash"]
    assert report["current_matches_assembled"] is True
    items = {c["item"]: c for c in report["checks"]}
    assert items["assembly manifest"]["ok"]
    assert items["attachment benchmark.csv"]["ok"]
    assert sum(1 for i in items if i.startswith("paper ")) == 18  # 6 papers x 3 versions
    assert all(c["ok"] for c in report["checks"])

    root: Path = cast(FastAPI, api.app).state.attachment_store.root
    digest = sha256_of_bytes(CSV)
    (root / digest[:2] / digest).write_bytes(CSV + b"tampered\n")
    tampered = api.get(f"/api/binders/{binder['id']}/verify").json()
    assert tampered["ok"] is False
    bad = next(c for c in tampered["checks"] if c["item"] == "attachment benchmark.csv")
    assert not bad["ok"] and "no longer matches its hash" in bad["detail"]
    assert next(c for c in tampered["checks"] if c["item"] == "assembly manifest")["ok"]


# --- 3F, 8.4: after assembly nothing is deleted; a change is an amendment ---------------------


def test_after_assembly_edits_need_a_reason_and_deletes_fail(api: TestClient) -> None:
    binder = complete_binder(api)
    api.post(f"/api/binders/{binder['id']}/assemble").raise_for_status()
    binder = api.get(f"/api/binders/{binder['id']}").json()
    c1 = next(p for s in binder["sections"] for p in s["papers"] if p["ref"] == "C-1")
    before = api.get(f"/api/papers/{c1['id']}").json()
    assert before["binder_state"] == "assembled"

    # ordinary edit: refused for want of a reason
    plain = api.patch(f"/api/papers/{c1['id']}", json={"conclusion": "Revised"})
    assert plain.status_code == 422 and "amendment reason" in plain.json()["detail"]
    # deletes: the attachment, the only deletable thing, is refused
    (attachment,) = before["attachments"]
    assert api.delete(f"/api/attachments/{attachment['id']}").status_code == 409
    # new papers and a new report date are refused too
    assert (
        api.post(
            f"/api/binders/{binder['id']}/papers", json={"ref": "D-9", "section": "D", "title": "x"}
        ).status_code
        == 409
    )
    assert (
        api.patch(f"/api/binders/{binder['id']}", json={"report_date": "2026-10-01"}).status_code
        == 409
    )

    # amendment: new version with reason, author and date; history untouched
    act_as(api, PARTNER)
    amended = api.patch(
        f"/api/papers/{c1['id']}",
        json={
            "conclusion": "Revised after subsequent event",
            "amendment_reason": "Subsequent event noted",
        },
    )
    assert amended.status_code == 200, amended.text
    body = amended.json()
    assert body["status"] == "draft" and body["current_version"] == 4
    assert body["versions"][:3] == before["versions"]
    v4 = body["versions"][3]
    assert v4["amendment_reason"] == "Subsequent event noted"
    assert v4["prepared_by"] == PARTNER and v4["prepared_at"]
    assert v4["body"]["conclusion"] == "Revised after subsequent event"
    status = assembly(api, binder["id"])
    assert [e["kind"] for e in status["events"]] == ["assembled", "amended"]
    assert status["events"][1]["reason"] == "Subsequent event noted"
    assert status["events"][1]["details"]["ref"] == "C-1"
    assert status["state"] == "assembled"  # the file stays frozen; the amendment is on record

    # the file no longer matches its assembled manifest until it is re-assembled
    assert (
        api.get(f"/api/binders/{binder['id']}/verify").json()["current_matches_assembled"] is False
    )
    assert ("unsigned_paper", "C-1") in {(b["kind"], b["ref"]) for b in status["blockers"]}
    full_chain(api, c1["id"])
    reassembled = api.post(f"/api/binders/{binder['id']}/assemble").json()
    assert (
        reassembled["assembly_hash"] != before
        and reassembled["assembly_hash"] != binder["assembly_hash"]
    )
    assert reassembled["events"][-1]["details"]["previous_file_hash"] == binder["assembly_hash"]
    assert (
        api.get(f"/api/binders/{binder['id']}/verify").json()["current_matches_assembled"] is True
    )


def test_attaching_after_assembly_is_an_amendment(api: TestClient) -> None:
    binder = complete_binder(api)
    api.post(f"/api/binders/{binder['id']}/assemble").raise_for_status()
    binder = api.get(f"/api/binders/{binder['id']}").json()
    x1 = next(p for s in binder["sections"] for p in s["papers"] if p["ref"] == "X-1")
    refused = upload(api, x1["id"], "late.pdf", PDF, expected=422)
    assert "amendment reason" in refused["detail"]
    amended = upload(api, x1["id"], "late.pdf", PDF, amendment_reason="Signed report received")
    assert amended["status"] == "draft"
    assert amended["versions"][-1]["amendment_reason"] == "Signed report received"
    assert amended["attachments"][0]["wp_version_id"] is not None


# --- 3G, 8.6: produce file ---------------------------------------------------------------------


def test_produce_file_is_one_archive_with_native_files_manifest_and_trail(api: TestClient) -> None:
    binder = complete_binder(api)
    assert api.get(f"/api/binders/{binder['id']}/produce").status_code == 409  # not assembled
    api.post(f"/api/binders/{binder['id']}/assemble").raise_for_status()
    act_as(api, PARTNER)
    response = api.get(f"/api/binders/{binder['id']}/produce")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["content-disposition"].endswith('-audit-file.zip"')

    data = response.content
    assert verify_archive(data) == []
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = set(archive.namelist())
        assert {"manifest.json", "binder.json", "audit_trail.json", "CHECKSUMS.sha256"} <= names
        manifest = json.loads(archive.read("manifest.json"))
        assert content_hash(manifest) == binder_hash(api, binder["id"])
        assert archive.read("papers/C-1/attachments/benchmark.csv") == CSV  # native bytes
        for ref in ("A-1", "B-1", "C-1", "W-1", "X-1", "Z-1"):
            assert f"papers/{ref}/paper.json" in names
            assert {f"papers/{ref}/versions/000{n}.json" for n in (1, 2, 3)} <= names
        v3 = json.loads(archive.read("papers/C-1/versions/0003.json"))
        assert v3["signed_off_by"] == PARTNER and v3["content_hash"]
        trail = json.loads(archive.read("audit_trail.json"))
        assert [e["kind"] for e in trail] == ["assembled"]
        checksums = archive.read("CHECKSUMS.sha256").decode()
        assert f"{sha256_of_bytes(CSV)}  papers/C-1/attachments/benchmark.csv" in checksums
    produced = assembly(api, binder["id"])["events"][-1]
    assert produced["kind"] == "produced" and produced["actor"] == PARTNER
    assert produced["details"]["archive_sha256"] == sha256_of_bytes(data)


def test_produce_includes_review_notes_per_paper_and_in_the_trail(api: TestClient) -> None:
    binder = complete_binder(api)
    c1 = next(p for s in binder["sections"] for p in s["papers"] if p["ref"] == "C-1")
    act_as(api, "reviewer@firm")
    note = api.post(f"/api/papers/{c1['id']}/review-notes", json={"text": "Justify the benchmark"})
    assert note.status_code == 201, note.text
    nid = note.json()["note_id"]
    api.post(
        f"/api/review-notes/{nid}/assign", json={"assigned_to": "preparer@firm"}
    ).raise_for_status()
    act_as(api, "preparer@firm")
    api.post(
        f"/api/review-notes/{nid}/respond", json={"text": "Revenue, per SA 320"}
    ).raise_for_status()
    act_as(api, "reviewer@firm")
    api.post(f"/api/review-notes/{nid}/clear").raise_for_status()
    act_as(api, PARTNER)
    api.post(f"/api/binders/{binder['id']}/assemble").raise_for_status()
    data = api.get(f"/api/binders/{binder['id']}/produce").content
    assert verify_archive(data) == []

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        notes = json.loads(archive.read("papers/C-1/review_notes.json"))
        assert len(notes) == 1
        assert notes[0]["text"] == "Justify the benchmark"
        assert notes[0]["state"] == "cleared" and notes[0]["open"] is False
        assert notes[0]["raised_by"] == "reviewer@firm"
        assert notes[0]["response"] == "Revenue, per SA 320"
        assert [s["state"] for s in notes[0]["steps"]] == [
            "raised",
            "assigned",
            "responded",
            "cleared",
        ]
        assert [s["actor"] for s in notes[0]["steps"]] == [
            "reviewer@firm",
            "reviewer@firm",
            "preparer@firm",
            "reviewer@firm",
        ]
        assert json.loads(archive.read("papers/A-1/review_notes.json")) == []  # always present

        trail = json.loads(archive.read("audit_trail.json"))
        note_entries = [e for e in trail if e["kind"] == "review_note"]
        assert [e["details"]["state"] for e in note_entries] == [
            "raised",
            "assigned",
            "responded",
            "cleared",
        ]
        assert all(
            e["details"]["ref"] == "C-1" and e["details"]["note_id"] == nid for e in note_entries
        )
        assert (
            note_entries[2]["actor"] == "preparer@firm"
            and note_entries[2]["details"]["text"] == "Revenue, per SA 320"
        )
        # chronological: every note step precedes the assembly event
        assert [e["kind"] for e in trail][-1] == "assembled"
        assert sorted(e["at"] for e in trail) == [e["at"] for e in trail]


def test_produce_gives_colliding_paper_references_distinct_folders(api: TestClient) -> None:
    # "D 1" and "D/1" both sanitise to "D_1"; without de-duplication one would overwrite the
    # other inside the archive and a paper would silently vanish from the produced file.
    binder = complete_binder(api)
    first = create_paper(api, binder["id"], ref="D 1", section="D", title="Cash")
    second = create_paper(api, binder["id"], ref="D/1", section="D", title="Bank")
    full_chain(api, first["id"])
    full_chain(api, second["id"])
    api.post(f"/api/binders/{binder['id']}/assemble").raise_for_status()
    data = api.get(f"/api/binders/{binder['id']}/produce").content
    assert verify_archive(data) == []
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        folders = json.loads(archive.read("binder.json"))["paper_folders"]
        assert folders["D 1"] != folders["D/1"]
        assert folders["D 1"] == "papers/D_1"
        assert (
            folders["D/1"].startswith("papers/D_1-")
            and len(folders["D/1"]) == len("papers/D_1-") + 8
        )
        titles = {
            json.loads(archive.read(f"{folders[ref]}/paper.json"))["ref"] for ref in ("D 1", "D/1")
        }
        assert titles == {"D 1", "D/1"}
        assert len([n for n in archive.namelist() if n.endswith("/paper.json")]) == 8


def test_produce_is_refused_between_an_amendment_and_re_assembly(api: TestClient) -> None:
    binder = complete_binder(api)
    api.post(f"/api/binders/{binder['id']}/assemble").raise_for_status()
    assert (
        api.get(f"/api/binders/{binder['id']}/assembly").json()["matches_recorded_manifest"] is True
    )
    assert api.get(f"/api/binders/{binder['id']}/produce").status_code == 200

    detail = api.get(f"/api/binders/{binder['id']}").json()
    c1 = next(p for s in detail["sections"] for p in s["papers"] if p["ref"] == "C-1")
    act_as(api, PARTNER)
    api.patch(
        f"/api/papers/{c1['id']}",
        json={"conclusion": "Revised", "amendment_reason": "Subsequent event"},
    ).raise_for_status()
    status = api.get(f"/api/binders/{binder['id']}/assembly").json()
    assert status["state"] == "assembled" and status["matches_recorded_manifest"] is False
    refused = api.get(f"/api/binders/{binder['id']}/produce")
    assert refused.status_code == 409
    assert "re-assemble, then produce" in refused.json()["detail"]
    events_before = [e["kind"] for e in status["events"]]
    assert "produced" not in events_before[-1:]  # the refusal recorded nothing

    full_chain(api, c1["id"])
    api.post(f"/api/binders/{binder['id']}/assemble").raise_for_status()
    assert (
        api.get(f"/api/binders/{binder['id']}/assembly").json()["matches_recorded_manifest"] is True
    )
    again = api.get(f"/api/binders/{binder['id']}/produce")
    assert again.status_code == 200
    assert verify_archive(again.content) == []


def binder_hash(api: TestClient, binder_id: str) -> str:
    digest: str = api.get(f"/api/binders/{binder_id}").json()["assembly_hash"]
    return digest


def test_a_tampered_archive_fails_verification() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("manifest.json", json.dumps({"papers": []}))
        archive.writestr("CHECKSUMS.sha256", f"{'0' * 64}  manifest.json\n")
    problems = verify_archive(buffer.getvalue())
    assert problems == ["manifest.json does not match its checksum"]


# --- 3G, 8.7: retention and purge -------------------------------------------------------------


def test_purge_is_refused_before_retention_and_recorded_after(api: TestClient) -> None:
    binder = complete_binder(api, report_date="2026-09-30")  # retained until 2033-09-30
    assert api.post(f"/api/binders/{binder['id']}/purge").status_code == 409  # not assembled
    api.post(f"/api/binders/{binder['id']}/assemble").raise_for_status()

    early = api.post(f"/api/binders/{binder['id']}/purge")
    assert early.status_code == 409
    assert "retention runs until 2033-09-30" in early.json()["detail"]
    assert assembly(api, binder["id"])["purge_allowed"] is False

    pretend_today(api, date(2033, 9, 29))
    assert api.post(f"/api/binders/{binder['id']}/purge").status_code == 409
    pretend_today(api, date(2033, 9, 30))
    assert assembly(api, binder["id"])["purge_allowed"] is True
    root: Path = cast(FastAPI, api.app).state.attachment_store.root
    assert any(root.rglob("*")) if root.exists() else False

    act_as(api, PARTNER)
    purged = api.post(f"/api/binders/{binder['id']}/purge")
    assert purged.status_code == 200, purged.text
    status = purged.json()
    assert status["state"] == "purged"
    event = status["events"][-1]
    assert event["kind"] == "purged" and event["actor"] == PARTNER and event["at"]
    assert event["details"]["attachment_rows_deleted"] == 1
    assert event["details"]["files_deleted"] == 1
    assert not [p for p in root.rglob("*") if p.is_file()]

    # content is gone; hashed metadata remains (D18)
    detail = api.get(f"/api/binders/{binder['id']}").json()
    assert detail["state"] == "purged" and detail["assembly_hash"] == status["assembly_hash"]
    c1 = next(p for s in detail["sections"] for p in s["papers"] if p["ref"] == "C-1")
    paper = api.get(f"/api/papers/{c1['id']}").json()
    assert paper["attachments"] == []
    assert len(paper["versions"]) == 3 and paper["versions"][0]["content_hash"]
    assert api.get(f"/api/binders/{binder['id']}/produce").status_code == 409
    assert api.post(f"/api/binders/{binder['id']}/purge").status_code == 409
    assert api.post(f"/api/papers/{c1['id']}/prepare").status_code == 409
