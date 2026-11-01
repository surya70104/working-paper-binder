"""The discussions and departures logs over the API (spec 2, 3H, 4; D28): record and list on
an open binder; after assembly an entry needs a reason, writes an amended event and puts
the file out of step with its recorded manifest until re-assembly; a purged binder takes
none; reads of an assembled file are in the access log; both logs are in the archive."""

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
from oak_binder.services.produce import verify_archive
from tests.conftest import PREPARER, act_as
from tests.helpers import PARTNER, complete_binder, create_binder

pytestmark = pytest.mark.db

DISCUSSION: dict[str, Any] = {
    "date": "2026-10-30",
    "participants": ["A. Partner", " R. Mehta (TCWG, Audit Committee Chair) ", ""],
    "matter": "Going concern: covenant breach at year end",
    "outcome": "Management to provide a 12-month cash-flow forecast",
}
DEPARTURE: dict[str, Any] = {
    "requirement": "SA 505 external confirmation of bank balances",
    "reason": "The bank did not respond within the reporting timetable",
    "alternative_procedure": "Agreed closing balances to statements and subsequent receipts",
    "approved_by": "partner@firm",
}


def post(
    api: TestClient, binder_id: str, kind: str, body: dict[str, Any], expected: int = 201
) -> dict[str, Any]:
    response = api.post(f"/api/binders/{binder_id}/{kind}", json=body)
    assert response.status_code == expected, f"{kind}: {response.status_code} {response.text}"
    result: dict[str, Any] = response.json()
    return result


def listing(api: TestClient, binder_id: str, kind: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = api.get(f"/api/binders/{binder_id}/{kind}").json()
    return rows


def test_record_and_list_on_an_open_binder(api: TestClient) -> None:
    binder = create_binder(api)
    act_as(api, PARTNER)
    d = post(api, binder["id"], "discussions", DISCUSSION)
    assert d["participants"] == ["A. Partner", "R. Mehta (TCWG, Audit Committee Chair)"]
    assert d["matter"] == DISCUSSION["matter"] and d["recorded_by"] == PARTNER and d["recorded_at"]
    later = post(
        api, binder["id"], "discussions", {**DISCUSSION, "date": "2026-10-31", "outcome": None}
    )
    assert later["outcome"] is None
    assert [x["date"] for x in listing(api, binder["id"], "discussions")] == [
        "2026-10-30",
        "2026-10-31",
    ]

    p = post(api, binder["id"], "departures", DEPARTURE)
    assert p["approved_by"] == "partner@firm" and p["recorded_by"] == PARTNER
    unapproved = post(api, binder["id"], "departures", {**DEPARTURE, "approved_by": None})
    assert unapproved["approved_by"] is None
    assert len(listing(api, binder["id"], "departures")) == 2

    # Validation: the spec's fields are required, blanks refused, a reason refused while open.
    assert (
        "at least one participant"
        in post(api, binder["id"], "discussions", {**DISCUSSION, "participants": [" "]}, 422)[
            "detail"
        ]
    )
    assert (
        "matter must not be blank"
        in post(api, binder["id"], "discussions", {**DISCUSSION, "matter": " "}, 422)["detail"]
    )
    assert (
        "requirement must not be blank"
        in post(api, binder["id"], "departures", {**DEPARTURE, "requirement": ""}, 422)["detail"]
    )
    assert (
        "amendment_reason applies to an assembled binder only"
        in post(api, binder["id"], "discussions", {**DISCUSSION, "amendment_reason": "x"}, 422)[
            "detail"
        ]
    )
    assert post(api, binder["id"], "discussions", {**DISCUSSION, "extra": 1}, 422)
    # The open binder's reads are not access-logged, and its manifest is unaffected either way.
    assert api.get(f"/api/binders/{binder['id']}/assembly").json()["access"] == []


def test_after_assembly_an_entry_is_an_amendment_and_production_waits_for_re_assembly(
    api: TestClient,
) -> None:
    binder = complete_binder(api)
    act_as(api, PARTNER)
    assembled = api.post(f"/api/binders/{binder['id']}/assemble").json()
    first_hash = assembled["assembly_hash"]
    assert api.get(f"/api/binders/{binder['id']}/produce").status_code == 200

    refused = post(api, binder["id"], "discussions", DISCUSSION, 422)
    assert "needs an amendment reason" in refused["detail"]
    entry = post(
        api,
        binder["id"],
        "discussions",
        {**DISCUSSION, "amendment_reason": "Audit committee met after the report date"},
    )
    status = api.get(f"/api/binders/{binder['id']}/assembly").json()
    event = status["events"][-1]
    assert event["kind"] == "amended" and event["actor"] == PARTNER
    assert event["reason"] == "Audit committee met after the report date"
    assert event["details"] == {
        "record": "discussion",
        "discussion_id": entry["id"],
        "date": "2026-10-30",
    }
    # The logs are part of the frozen file: the recorded manifest no longer describes it.
    assert status["matches_recorded_manifest"] is False
    blocked = api.get(f"/api/binders/{binder['id']}/produce")
    assert blocked.status_code == 409 and "re-assemble" in blocked.json()["detail"]
    verify = api.get(f"/api/binders/{binder['id']}/verify").json()
    assert verify["current_matches_assembled"] is False

    reassembled = api.post(f"/api/binders/{binder['id']}/assemble")
    assert reassembled.status_code == 200, reassembled.text
    second_hash = reassembled.json()["assembly_hash"]
    assert second_hash != first_hash
    manifest = reassembled.json()["manifest"]
    assert [d["matter"] for d in manifest["discussions"]] == [DISCUSSION["matter"]]
    assert "departures" not in manifest  # none yet: the key appears only once any exist

    post(
        api, binder["id"], "departures", {**DEPARTURE, "amendment_reason": "Approval recorded late"}
    )
    assert api.get(f"/api/binders/{binder['id']}/produce").status_code == 409
    api.post(f"/api/binders/{binder['id']}/assemble").raise_for_status()
    produced = api.get(f"/api/binders/{binder['id']}/produce")
    assert produced.status_code == 200
    assert verify_archive(produced.content) == []
    with zipfile.ZipFile(io.BytesIO(produced.content)) as archive:
        discussions = json.loads(archive.read("discussions.json"))
        departures = json.loads(archive.read("departures.json"))
        assert [d["participants"] for d in discussions] == [
            ["A. Partner", "R. Mehta (TCWG, Audit Committee Chair)"]
        ]
        assert departures[0]["alternative_procedure"] == DEPARTURE["alternative_procedure"]
        trail = json.loads(archive.read("audit_trail.json"))
        amended = [e for e in trail if e["kind"] == "amended"]
        assert {e["details"]["record"] for e in amended} == {"discussion", "departure"}
        checksums = archive.read("CHECKSUMS.sha256").decode()
        assert "  discussions.json\n" in checksums and "  departures.json\n" in checksums


def test_reads_of_an_assembled_files_logs_are_in_the_access_log(api: TestClient) -> None:
    binder = complete_binder(api)
    act_as(api, PARTNER)
    api.post(f"/api/binders/{binder['id']}/assemble").raise_for_status()
    act_as(api, "quality.reviewer@firm")
    assert api.get(f"/api/binders/{binder['id']}/discussions").status_code == 200
    assert api.get(f"/api/binders/{binder['id']}/departures").status_code == 200
    rows = api.get(f"/api/binders/{binder['id']}/assembly").json()["access"]
    assert [r["action"] for r in rows if r["user"] == "quality.reviewer@firm"] == [
        "discussions",
        "departures",
        "assembly status",
    ]
    act_as(api, None)
    assert api.get(f"/api/binders/{binder['id']}/discussions").status_code == 503


def test_a_purged_binder_takes_no_entries(api: TestClient) -> None:
    binder = complete_binder(api, report_date="2026-09-30")
    act_as(api, PARTNER)
    api.post(f"/api/binders/{binder['id']}/assemble").raise_for_status()
    cast(FastAPI, api.app).dependency_overrides[deps.today] = lambda: date(2033, 10, 1)
    try:
        api.post(f"/api/binders/{binder['id']}/purge").raise_for_status()
        refused = post(
            api, binder["id"], "departures", {**DEPARTURE, "amendment_reason": "late"}, 409
        )
        assert "purged" in refused["detail"]
        assert listing(api, binder["id"], "departures") == []
    finally:
        cast(FastAPI, api.app).dependency_overrides.pop(deps.today, None)
    act_as(api, PREPARER)


def test_an_already_assembled_file_without_entries_keeps_its_recorded_hash(api: TestClient) -> None:
    # The manifest lists the logs only once any exist, so files assembled before Stage A still
    # match what they recorded.
    binder = complete_binder(api)
    act_as(api, PARTNER)
    api.post(f"/api/binders/{binder['id']}/assemble").raise_for_status()
    status = api.get(f"/api/binders/{binder['id']}/assembly").json()
    assert status["matches_recorded_manifest"] is True
    assert "discussions" not in status["manifest"] and "departures" not in status["manifest"]
