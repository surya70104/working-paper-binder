"""Pass 2 close-out (Stage G, D34), against oak_binder_test: the archive carries every Pass 1 and
Pass 2 member, the cross-reference map member equals the map endpoint and is identical whether
or not the Spine answers, the manifest and hash are untouched, and the assembly blocker
inventory is exactly the specification's four plus the decided additions."""

from __future__ import annotations

import copy
import io
import json
import re
import zipfile
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from oak_binder.hashing import content_hash
from oak_binder.services import spine_papers
from oak_binder.services.templates import TEMPLATES_DIR, parse_template
from tests.conftest import PREPARER, act_as, use_spine
from tests.fake_spine import ENGAGEMENT_ID, LOCKED_VERSION_ID, FakeSpine
from tests.helpers import (
    PARTNER,
    PDF,
    complete_binder,
    create_paper,
    generated_fixture,
    step,
    upload,
)

pytestmark = pytest.mark.db

EXPECTED_BINDER_MEMBERS = {
    "manifest.json",
    "binder.json",
    "audit_trail.json",
    "access_log.json",
    "discussions.json",
    "departures.json",
    "cross_reference_map.json",
    "CHECKSUMS.sha256",
}
EXPECTED_PAPER_MEMBERS = {
    "paper.json",
    "review_notes.json",
    "reviews.json",
    "cross_references.json",
}

# Spec 3F / 8.3 names four blockers; Pass 1 added the undated report (D17), Stage B the Spine
# link checks (D29). Stages C-G added none.
BLOCKER_INVENTORY = {
    "unsigned_paper",
    "open_review_notes",
    "broken_reference",
    "missing_required_paper",
    "report_not_dated",
    "spine_version_unlocked",
    "spine_version_missing",
    "spine_unreachable",
    "spine_version_not_verified",
}


def use_area_map(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = copy.deepcopy(json.loads((TEMPLATES_DIR / "statutory.json").read_text(encoding="utf-8")))
    raw["areas"] = {"D": {"heads": ["BS.A.1"]}}
    monkeypatch.setattr(
        spine_papers, "load_template", lambda name: parse_template("statutory", raw)
    )


def members_of(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def complete_pass_2_binder(api: TestClient, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """A binder exercising every Pass 2 feature: logs, Spine link, lead schedule and chain,
    a sampling paper from the intake, review levels, cross-references of every kind."""
    use_spine(api)
    use_area_map(monkeypatch)
    binder = complete_binder(api)
    bid = binder["id"]
    act_as(api, PREPARER)
    api.patch(
        f"/api/binders/{bid}", json={"review_levels": ["senior", "partner"]}
    ).raise_for_status()
    api.patch(
        f"/api/binders/{bid}",
        json={
            "spine_engagement_id": str(ENGAGEMENT_ID),
            "spine_version_id": str(LOCKED_VERSION_ID),
        },
    ).raise_for_status()
    api.post(
        f"/api/binders/{bid}/discussions",
        json={
            "date": "2026-10-30",
            "participants": ["A. Partner", "R. Mehta (TCWG)"],
            "matter": "Going concern",
            "outcome": None,
        },
    ).raise_for_status()
    api.post(
        f"/api/binders/{bid}/departures",
        json={
            "requirement": "SA 505",
            "reason": "No bank reply",
            "alternative_procedure": "Agreed to statements",
            "approved_by": None,
        },
    ).raise_for_status()
    [lead] = api.post(
        f"/api/binders/{bid}/spine-papers/lead-schedules", json={"areas": ["D"]}
    ).json()
    chain = api.post(f"/api/binders/{bid}/spine-papers/adjustment-chain").json()
    cash = create_paper(api, bid, ref="D-1", section="D", title="Cash and bank")
    [doc] = upload(api, cash["id"], "statement.pdf", PDF)["attachments"]
    api.post(
        f"/api/papers/{cash['id']}/xrefs", json={"to_wp": lead["id"], "direction": "to"}
    ).raise_for_status()
    api.post(
        f"/api/papers/{cash['id']}/xrefs",
        json={"to_vault_doc": doc["vault_doc_id"], "direction": "to"},
    ).raise_for_status()
    fixture = generated_fixture("sampling")
    sampling = api.post(f"/api/binders/{bid}/generated-papers", json=fixture).json()
    for paper in (lead, chain, cash, sampling):
        if paper["conclusion"] is None:
            api.patch(
                f"/api/papers/{paper['id']}", json={"conclusion": "Satisfactory."}
            ).raise_for_status()
        act_as(api, PREPARER)
        step(api, paper["id"], "prepare")
        step(api, paper["id"], "submit")
        act_as(api, "senior@firm")
        step(api, paper["id"], "review")
        act_as(api, PARTNER)
        step(api, paper["id"], "review")
        step(api, paper["id"], "sign-off")
    act_as(api, PARTNER)
    assembled = api.post(f"/api/binders/{bid}/assemble")
    assert assembled.status_code == 200, assembled.text
    return {
        "binder": binder,
        "assembled": assembled.json(),
        "papers": [lead, chain, cash, sampling],
    }


def test_the_archive_carries_every_pass_1_and_pass_2_member(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    done = complete_pass_2_binder(api, monkeypatch)
    bid = done["binder"]["id"]
    produced = api.get(f"/api/binders/{bid}/produce")
    assert produced.status_code == 200
    members = members_of(produced.content)
    assert EXPECTED_BINDER_MEMBERS <= set(members)
    folders = {
        n.rsplit("/", 1)[0]
        for n in members
        if n.startswith("papers/") and n.endswith("/paper.json")
    }
    assert len(folders) == len(done["assembled"]["manifest"]["papers"])
    for folder in folders:
        assert {f"{folder}/{m}" for m in EXPECTED_PAPER_MEMBERS} <= set(members), folder
        assert any(n.startswith(f"{folder}/versions/") for n in members), folder
    assert json.loads(members["discussions.json"])[0]["matter"] == "Going concern"
    assert json.loads(members["departures.json"])[0]["requirement"] == "SA 505"
    # Provenance and review history ride in the per-paper members.
    sampling_folder = next(
        f for f in folders if json.loads(members[f"{f}/paper.json"])["ref"] == "D-3"
    )
    assert json.loads(members[f"{sampling_folder}/paper.json"])["generated_by"] == "sampling"
    body = json.loads(members[f"{sampling_folder}/versions/0001.json"])["body"]
    assert body["generated"]["source"] == "sampling"
    assert body["generated"]["payload"]["inputs"]["sample_size"] == 60
    reviews = json.loads(members[f"{sampling_folder}/reviews.json"])
    assert reviews["configured_levels"] == ["senior", "partner"]
    assert [r["level"] for r in reviews["cycles"][0]["level_reviews"]] == ["senior", "partner"]
    lead_folder = next(f for f in folders if json.loads(members[f"{f}/paper.json"])["ref"] == "D-L")
    assert json.loads(members[f"{lead_folder}/paper.json"])["generated_by"] == "spine"
    # The CHECKSUMS member covers the new member like every other.
    checksums = members["CHECKSUMS.sha256"].decode("utf-8")
    assert "  cross_reference_map.json\n" in checksums


def test_the_archive_map_equals_the_endpoint_and_is_identical_with_the_spine_down(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    done = complete_pass_2_binder(api, monkeypatch)
    bid = done["binder"]["id"]
    state = cast(FastAPI, api.app).state  # the double is installed on the app state
    endpoint = api.get(f"/api/binders/{bid}/xref-map").json()
    assert endpoint["available"] is True and endpoint["lines"]  # the lead schedule ties BS.A.1
    up = members_of(api.get(f"/api/binders/{bid}/produce").content)
    archived = json.loads(up["cross_reference_map.json"])
    assert archived == json.loads(json.dumps(endpoint))
    assert archived["lines"][0]["head_id"] == "BS.A.1"
    [lead_node] = archived["lines"][0]["papers"]
    assert lead_node["ref"] == "D-L" and lead_node["role"] == "lead_schedule"
    assert [p["ref"] for p in lead_node["papers"]] == ["D-1"]
    assert lead_node["papers"][0]["documents"][0]["filename"] == "statement.pdf"
    assert archived["broken"] == 0 and archived["unchecked"] == 0
    # The Spine down, timing out, and absent: the member does not change by a byte.
    client_before = state.spine_client
    failing = FakeSpine()
    failing.fail_with = 503
    state.spine_client = failing.client()
    down = members_of(api.get(f"/api/binders/{bid}/produce").content)
    timing = FakeSpine()
    timing.time_out = True
    state.spine_client = timing.client()
    timed = members_of(api.get(f"/api/binders/{bid}/produce").content)
    state.spine_client = None
    absent = members_of(api.get(f"/api/binders/{bid}/produce").content)
    state.spine_client = client_before
    for other in (down, timed, absent):
        assert other["cross_reference_map.json"] == up["cross_reference_map.json"]
        assert other["manifest.json"] == up["manifest.json"]
        for name in up:
            if "/versions/" in name or name.endswith("cross_references.json"):
                assert other[name] == up[name], name
    assert failing.non_get_calls() == [] and timing.non_get_calls() == []


def test_the_manifest_and_hash_are_untouched_by_the_new_member(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    done = complete_pass_2_binder(api, monkeypatch)
    manifest = done["assembled"]["manifest"]
    assert "cross_reference_map" not in manifest and "review_levels" not in manifest
    assert content_hash(manifest) == done["assembled"]["assembly_hash"]
    produced = members_of(api.get(f"/api/binders/{done['binder']['id']}/produce").content)
    assert json.loads(produced["manifest.json"]) == json.loads(json.dumps(manifest, default=str))
    assert (
        api.get(f"/api/binders/{done['binder']['id']}/verify").json()["current_matches_assembled"]
        is True
    )


def test_the_blocker_inventory_is_exactly_the_decided_set() -> None:
    source = (
        Path(__file__).parents[1] / "src" / "oak_binder" / "services" / "assembly.py"
    ).read_text(encoding="utf-8")
    kinds = set(re.findall(r'Blocker\(\s*"([a-z_]+)"', source))
    assert kinds == BLOCKER_INVENTORY


def test_a_pass_1_style_binder_produces_the_same_members_with_an_unavailable_map(
    api: TestClient,
) -> None:
    """No Spine, no link, no generated paper: the map member says lines cannot be checked, as the
    screen does, and every Pass 2 member is still present."""
    binder = complete_binder(api)
    act_as(api, PARTNER)
    assert api.post(f"/api/binders/{binder['id']}/assemble").status_code == 200
    members = members_of(api.get(f"/api/binders/{binder['id']}/produce").content)
    assert EXPECTED_BINDER_MEMBERS <= set(members)
    archived = json.loads(members["cross_reference_map.json"])
    assert archived["available"] is False and "not linked" in archived["reason"]
    assert archived["lines"] == [] and archived["total_references"] == 0
    assert (
        json.loads(members["discussions.json"]) == []
        and json.loads(members["departures.json"]) == []
    )
