"""Freshness and regeneration of Spine papers (Stage E step E4, D32; decisions 6, 8, 15 and
the reference-ownership rule). Against oak_binder_test with the Spine double."""

from __future__ import annotations

import copy
import io
import json
import uuid
import zipfile
from typing import Any

import pytest
from fastapi.testclient import TestClient

from oak_binder.hashing import content_hash
from oak_binder.services import spine_papers
from oak_binder.services.templates import TEMPLATES_DIR, parse_template
from tests.conftest import PREPARER, REVIEWER, act_as, use_spine
from tests.fake_spine import (
    ENGAGEMENT_ID,
    LOCKED_HASH,
    LOCKED_VERSION_ID,
    OPEN_VERSION_ID,
    FakeSpine,
)
from tests.helpers import PARTNER, complete_binder, create_binder, create_paper, full_chain, step

pytestmark = pytest.mark.db

AREAS: dict[str, dict[str, Any]] = {"D": {"heads": ["BS.A.1"]}, "G": {"heads": ["BS.L.1"]}}


def use_area_map(monkeypatch: pytest.MonkeyPatch, areas: dict[str, Any] = AREAS) -> None:
    raw = copy.deepcopy(json.loads((TEMPLATES_DIR / "statutory.json").read_text(encoding="utf-8")))
    raw["areas"] = areas
    template = parse_template("statutory", raw)
    monkeypatch.setattr(spine_papers, "load_template", lambda name: template)


def link(api: TestClient, binder_id: str, version: uuid.UUID = LOCKED_VERSION_ID) -> None:
    response = api.patch(
        f"/api/binders/{binder_id}",
        json={"spine_engagement_id": str(ENGAGEMENT_ID), "spine_version_id": str(version)},
    )
    assert response.status_code == 200, response.text


def generate(api: TestClient, binder_id: str, areas: list[str]) -> list[dict[str, Any]]:
    response = api.post(
        f"/api/binders/{binder_id}/spine-papers/lead-schedules", json={"areas": areas}
    )
    assert response.status_code == 201, response.text
    result: list[dict[str, Any]] = response.json()
    return result


def chain(api: TestClient, binder_id: str) -> dict[str, Any]:
    response = api.post(f"/api/binders/{binder_id}/spine-papers/adjustment-chain")
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


def regenerate(api: TestClient, paper_id: str, expected: int = 200) -> Any:
    response = api.post(f"/api/papers/{paper_id}/regenerate")
    assert response.status_code == expected, f"{response.status_code} {response.text}"
    return response.json()


def status_of(api: TestClient, binder_id: str) -> dict[str, Any]:
    result: dict[str, Any] = api.get(f"/api/binders/{binder_id}/spine-papers").json()
    return result


def relock_other_version(spine: FakeSpine) -> None:
    """Lock the double's second version so the binder can be re-linked to another locked one."""
    spine.lock(OPEN_VERSION_ID)


def test_binder_written_references_are_created_by_the_spine_and_the_person_is_received_by(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_spine(api)
    use_area_map(monkeypatch)
    binder = create_binder(api)
    link(api, binder["id"])
    create_paper(api, binder["id"], ref="D-1", section="D", title="Cash")
    [lead] = generate(api, binder["id"], ["D"])
    adj = chain(api, binder["id"])
    for paper in (lead, adj):
        assert paper["generated"]["received_by"] == PREPARER
        assert paper["xrefs"] and all(x["created_by"] == "oak_spine" for x in paper["xrefs"])
    assert lead["generated"]["payload"]["inputs"]["references_written"] == {"fs_lines": ["BS.A.1"]}
    assert adj["generated"]["payload"]["inputs"]["references_written"] == {"papers": ["D-1"]}


def test_freshness_is_current_then_stale_after_a_relink_and_not_checked_when_the_spine_is_down(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    spine = use_spine(api)
    use_area_map(monkeypatch)
    binder = create_binder(api)
    link(api, binder["id"])
    generate(api, binder["id"], ["D"])
    chain(api, binder["id"])

    status = status_of(api, binder["id"])
    d = next(a for a in status["areas"] if a["code"] == "D")
    assert d["state"] == "current" and d["detail"] is None
    assert (
        d["recorded_version_id"] == str(LOCKED_VERSION_ID)
        and d["recorded_version_label"] == "Final"
    )
    assert status["chain"]["state"] == "current"

    relock_other_version(spine)
    link(api, binder["id"], OPEN_VERSION_ID)
    status = status_of(api, binder["id"])
    d = next(a for a in status["areas"] if a["code"] == "D")
    assert d["state"] == "stale"
    assert "built from Spine version 'Final'" in d["detail"]
    assert f"now linked to 'Post-lock work' ({OPEN_VERSION_ID})" in d["detail"]
    assert status["chain"]["state"] == "stale" and status["chain"]["detail"]
    # Stale is information: the assembly status lists it and nothing blocks because of it.
    assembly = api.get(f"/api/binders/{binder['id']}/assembly").json()
    notes = [n for n in assembly["not_checked"] if n.startswith("Spine paper")]
    assert len(notes) == 2 and all(
        "information; regenerate while the binder is open" in n for n in notes
    )
    assert not [b for b in assembly["blockers"] if "spine_paper" in b["kind"]]

    spine.fail_with = 503
    status = status_of(api, binder["id"])
    d = next(a for a in status["areas"] if a["code"] == "D")
    # Re-linked to another id: stale is known from the ids alone, even with the Spine down.
    assert d["state"] == "stale"
    spine.fail_with = None
    link(api, binder["id"], LOCKED_VERSION_ID)
    spine.fail_with = 503
    d = next(a for a in status_of(api, binder["id"])["areas"] if a["code"] == "D")
    assert d["state"] == "not_checked" and "could not answer" in d["detail"]
    regenerate(api, d["paper_id"], 503)


def test_regeneration_rewrites_the_spines_fields_keeps_the_persons_and_the_history(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    spine = use_spine(api)
    use_area_map(monkeypatch)
    binder = create_binder(api)
    link(api, binder["id"])
    [lead] = generate(api, binder["id"], ["D"])
    api.patch(
        f"/api/papers/{lead['id']}",
        json={"objective": "Agree cash.", "procedure": "Traced.", "conclusion": "Fair."},
    ).raise_for_status()
    signed = full_chain(api, lead["id"])
    assert len(signed["versions"]) == 3
    first_bodies = [v["body"] for v in signed["versions"]]
    first_hashes = [v["content_hash"] for v in signed["versions"]]
    act_as(api, PREPARER)

    # Nothing changed: a repeat is refused as one paper per run.
    refused = regenerate(api, lead["id"], 409)
    assert "one paper per run" in refused["detail"]

    relock_other_version(spine)
    link(api, binder["id"], OPEN_VERSION_ID)
    done = regenerate(api, lead["id"])
    assert done["status"] == "draft" and done["current_version"] == 3  # versions untouched
    assert (
        done["objective"] == "Agree cash."
        and done["procedure"] == "Traced."
        and done["conclusion"] == "Fair."
    )
    block = done["generated"]["payload"]["spine"]
    assert block["version_id"] == str(OPEN_VERSION_ID) and block["version_hash"] == "e" * 64
    assert done["generated"]["run_id"] == f"{binder['id']}/{OPEN_VERSION_ID}/{'e' * 64}/D"
    assert done["generated"]["received_by"] == PREPARER
    regen = done["generated"]["payload"]["inputs"]["regeneration"]
    assert regen["previous_run_id"] == f"{binder['id']}/{LOCKED_VERSION_ID}/{LOCKED_HASH}/D"
    assert regen["previous_version_id"] == str(LOCKED_VERSION_ID)
    assert regen["kept_by_person"] == ["objective", "procedure", "conclusion"]
    assert done["regeneration"]["references"] == {
        "added": [],
        "removed": [],
        "kept": ["BS.A.1"],
        "for_review": [],
    }
    assert done["regeneration"]["previous_run_id"] == regen["previous_run_id"]
    # Earlier versions keep their bodies and hashes, with the first provenance row embedded.
    again = api.get(f"/api/papers/{lead['id']}").json()
    assert [v["body"] for v in again["versions"]] == first_bodies
    assert [v["content_hash"] for v in again["versions"]] == first_hashes
    assert all(
        v["body"]["generated"]["payload"]["spine"]["version_id"] == str(LOCKED_VERSION_ID)
        for v in again["versions"]
    )
    # The next prepare writes version 4 embedding the second row.
    prepared = step(api, lead["id"], "prepare")
    v4 = prepared["versions"][3]
    assert v4["version"] == 4 and v4["body"]["generated"]["payload"]["spine"]["version_id"] == str(
        OPEN_VERSION_ID
    )
    assert v4["content_hash"] == content_hash(v4["body"])
    assert (
        next(a for a in status_of(api, binder["id"])["areas"] if a["code"] == "D")["state"]
        == "current"
    )
    assert spine.non_get_calls() == []


def test_regeneration_removes_only_binder_owned_references_and_keeps_every_manual_one(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    spine = use_spine(api)
    use_area_map(monkeypatch)
    binder = create_binder(api)
    link(api, binder["id"])
    [lead] = generate(api, binder["id"], ["D"])  # Binder wrote D-L → BS.A.1
    # A person adds, by hand, a second reference to the same line and one to another line.
    api.post(
        f"/api/papers/{lead['id']}/xrefs", json={"to_fs_line": "BS.A.1", "direction": "to"}
    ).raise_for_status()
    api.post(
        f"/api/papers/{lead['id']}/xrefs", json={"to_fs_line": "BS.L.1", "direction": "to"}
    ).raise_for_status()
    before = {
        (x["to_fs_line"], x["created_by"])
        for x in api.get(f"/api/papers/{lead['id']}/xrefs").json()
    }
    assert before == {("BS.A.1", "oak_spine"), ("BS.A.1", PREPARER), ("BS.L.1", PREPARER)}

    # The new version serves no presentation line under BS.A.1: the Binder's own reference goes,
    # the person's two stay, and the one to a line outside the new block is listed for review.
    import tests.fake_spine as fake

    original = fake.presentation_record

    def without_cash(version_id: uuid.UUID, locked: bool) -> dict[str, Any]:
        record = original(version_id, locked)
        record["balance_sheet"]["lines"] = [
            ln for ln in record["balance_sheet"]["lines"] if ln.get("head_id") != "BS.A.1"
        ]
        return record

    monkeypatch.setattr(fake, "presentation_record", without_cash)
    relock_other_version(spine)
    link(api, binder["id"], OPEN_VERSION_ID)
    done = regenerate(api, lead["id"])
    assert done["regeneration"]["references"] == {
        "added": [],
        "removed": ["BS.A.1"],
        "kept": [],
        "for_review": ["BS.A.1", "BS.L.1"],
    }
    after = {
        (x["to_fs_line"], x["created_by"])
        for x in api.get(f"/api/papers/{lead['id']}/xrefs").json()
    }
    assert after == {("BS.A.1", PREPARER), ("BS.L.1", PREPARER)}
    assert done["generated"]["payload"]["inputs"]["regeneration"]["references"]["removed"] == [
        "BS.A.1"
    ]


def test_a_reference_without_the_marker_is_never_removed_only_reported(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The conservative rule for any reference whose Binder ownership is not reliably
    established: a reference to a target of the previous block but created by a person."""
    spine = use_spine(api)
    use_area_map(monkeypatch, {"G": {"heads": ["BS.L.1"]}, "D": {"heads": ["BS.A.1"]}})
    binder = create_binder(api)
    link(api, binder["id"])
    [lead] = generate(api, binder["id"], ["G"])
    [own] = api.get(f"/api/papers/{lead['id']}/xrefs").json()
    assert own["created_by"] == "oak_spine" and own["to_fs_line"] == "BS.L.1"
    # Simulate a legacy or manual reference to the very same target: remove the Binder's and
    # let a person add one.
    assert api.delete(f"/api/xrefs/{own['id']}").status_code == 204
    api.post(
        f"/api/papers/{lead['id']}/xrefs", json={"to_fs_line": "BS.L.1", "direction": "to"}
    ).raise_for_status()

    import tests.fake_spine as fake

    original = fake.presentation_record
    monkeypatch.setattr(
        fake,
        "presentation_record",
        lambda version_id, locked: {
            **original(version_id, locked),
            "balance_sheet": {
                "lines": [
                    ln
                    for ln in original(version_id, locked)["balance_sheet"]["lines"]
                    if ln.get("head_id") != "BS.L.1"
                ]
            },
        },
    )
    relock_other_version(spine)
    link(api, binder["id"], OPEN_VERSION_ID)
    done = regenerate(api, lead["id"])
    assert done["regeneration"]["references"] == {
        "added": [],
        "removed": [],
        "kept": [],
        "for_review": ["BS.L.1"],
    }
    [kept] = api.get(f"/api/papers/{lead['id']}/xrefs").json()
    assert kept["to_fs_line"] == "BS.L.1" and kept["created_by"] == PREPARER
    # Under the new version that line is unknown: the existing broken-reference rule applies.
    assert "not a line of the linked Spine version" in kept["broken"]


def test_the_chain_regenerates_with_its_references_following_exact_matches(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    spine = use_spine(api)
    binder = create_binder(api)
    link(api, binder["id"])
    create_paper(api, binder["id"], ref="D-1", section="D", title="Cash")
    adj = chain(api, binder["id"])
    assert [x["to_ref"] for x in adj["xrefs"]] == ["D-1"]
    api.patch(f"/api/papers/{adj['id']}", json={"conclusion": "Immaterial."}).raise_for_status()
    # D-9 now exists: on regeneration the Binder adds a reference to it and keeps D-1.
    create_paper(api, binder["id"], ref="D-9", section="D", title="Related parties")
    relock_other_version(spine)
    link(api, binder["id"], OPEN_VERSION_ID)
    done = regenerate(api, adj["id"])
    assert done["conclusion"] == "Immaterial."
    assert done["regeneration"]["references"] == {
        "added": ["D-9"],
        "removed": [],
        "kept": ["D-1"],
        "for_review": [],
    }
    assert sorted(x["to_ref"] for x in done["xrefs"]) == ["D-1", "D-9"]
    assert all(x["created_by"] == "oak_spine" for x in done["xrefs"])
    assert done["generated"]["payload"]["inputs"]["working_paper_refs"] == {
        "D-1": "D-1",
        "D-9": "D-9",
    }


def test_regeneration_is_refused_by_name_where_it_cannot_run(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    spine = use_spine(api)
    use_area_map(monkeypatch)
    binder = complete_binder(api)
    link(api, binder["id"])
    [lead] = generate(api, binder["id"], ["D"])
    hand_made = next(p for s in binder["sections"] for p in s["papers"] if p["ref"] == "C-1")
    assert (
        "was not generated from the Financial Spine"
        in regenerate(api, hand_made["id"], 422)["detail"]
    )
    spine.fail_with = 503
    assert "could not answer" in regenerate(api, lead["id"], 503)["detail"]
    spine.fail_with = None
    # Re-linked while open, then assembled without regenerating: the stale paper is frozen as
    # information, assembly is not blocked by it, and regeneration is refused afterwards.
    relock_other_version(spine)
    link(api, binder["id"], OPEN_VERSION_ID)
    api.patch(f"/api/papers/{lead['id']}", json={"conclusion": "Cash agrees."}).raise_for_status()
    full_chain(api, lead["id"])
    act_as(api, PARTNER)
    assembled = api.post(f"/api/binders/{binder['id']}/assemble")
    assert assembled.status_code == 200, assembled.text
    notes = [n for n in assembled.json()["not_checked"] if n.startswith("Spine paper D-L")]
    assert len(notes) == 1 and "built from Spine version 'Final'" in notes[0]
    assert not [b for b in assembled.json()["blockers"] if "spine_paper" in b["kind"]]
    refused = regenerate(api, lead["id"], 409)
    assert "the binder is assembled" in refused["detail"]
    # The Pass 1 amendment path still applies to the paper's unlocked fields.
    amended = api.patch(
        f"/api/papers/{lead['id']}", json={"conclusion": "Revised.", "amendment_reason": "review"}
    )
    assert amended.status_code == 200, amended.text
    # An amended paper is signed off again before the file is re-assembled (spec 3F).
    full_chain(api, lead["id"])  # the amendment returned it to draft; the chain runs again
    act_as(api, PARTNER)
    # The archive is the same whether or not the Spine answers.
    api.post(f"/api/binders/{binder['id']}/assemble").raise_for_status()
    produced = api.get(f"/api/binders/{binder['id']}/produce")
    assert produced.status_code == 200
    spine.fail_with = 503
    again = api.get(f"/api/binders/{binder['id']}/produce")
    assert again.status_code == 200

    def members(data: bytes) -> dict[str, bytes]:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            return {
                n: z.read(n)
                for n in z.namelist()
                if "/versions/" in n or n.endswith("cross_references.json")
            }

    assert members(produced.content) == members(again.content)
    act_as(api, REVIEWER)


def test_the_paper_endpoint_carries_freshness_for_spine_papers_only(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Step E5: the paper screen reads freshness from the paper itself (one source of truth)."""
    spine = use_spine(api)
    use_area_map(monkeypatch)
    binder = create_binder(api)
    link(api, binder["id"])
    hand_made = create_paper(api, binder["id"], ref="D-1", section="D", title="Cash")
    assert hand_made["generated"] is None
    [lead] = generate(api, binder["id"], ["D"])
    assert lead["generated"]["freshness"] == {
        "state": "current",
        "detail": None,
        "recorded_version_id": str(LOCKED_VERSION_ID),
        "recorded_version_label": "Final",
    }
    assert api.get(f"/api/papers/{lead['id']}/generation").json()["freshness"]["state"] == "current"
    relock_other_version(spine)
    link(api, binder["id"], OPEN_VERSION_ID)
    fresh = api.get(f"/api/papers/{lead['id']}").json()["generated"]["freshness"]
    assert fresh["state"] == "stale" and "now linked to 'Post-lock work'" in fresh["detail"]
    spine.fail_with = 503
    link_back = api.get(f"/api/papers/{lead['id']}").json()["generated"]["freshness"]
    assert link_back["state"] == "stale"  # the ids alone decide
    spine.fail_with = None
    link(api, binder["id"], LOCKED_VERSION_ID)
    spine.fail_with = 503
    fresh = api.get(f"/api/papers/{lead['id']}").json()["generated"]["freshness"]
    assert fresh["state"] == "not_checked" and "could not answer" in fresh["detail"]
    spine.fail_with = None
    # Another module's paper carries no freshness at all.
    from tests.test_api_generated import deliver, fixture

    sampling = deliver(api, binder["id"], fixture("sampling"))
    assert sampling["generated"]["freshness"] is None


def test_a_target_with_a_binder_and_a_manual_reference_is_reported_once_and_both_rows_stay(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Audit follow-up: the regeneration record names each target once; the rows themselves
    are classified one by one, so a person's duplicate of the Binder's reference survives."""
    spine = use_spine(api)
    use_area_map(monkeypatch)
    binder = create_binder(api)
    link(api, binder["id"])
    [lead] = generate(api, binder["id"], ["D"])  # Binder: D-L → BS.A.1
    api.post(
        f"/api/papers/{lead['id']}/xrefs", json={"to_fs_line": "BS.A.1", "direction": "to"}
    ).raise_for_status()
    api.post(
        f"/api/papers/{lead['id']}/xrefs", json={"to_fs_line": "PL.R.1", "direction": "to"}
    ).raise_for_status()
    api.post(
        f"/api/papers/{lead['id']}/xrefs",
        json={
            "to_wp": create_paper(api, binder["id"], ref="D-2", section="D", title="x")["id"],
            "direction": "to",
        },
    ).raise_for_status()
    relock_other_version(spine)
    link(api, binder["id"], OPEN_VERSION_ID)  # BS.A.1 still served by the new version
    done = regenerate(api, lead["id"])
    assert done["regeneration"]["references"] == {
        "added": [],
        "removed": [],
        "kept": ["BS.A.1"],  # once, although two references point at it
        "for_review": ["PL.R.1", "D-2"],
    }
    after = sorted((x["to_fs_line"] or x["to_ref"], x["created_by"]) for x in done["xrefs"])
    assert after == [
        ("BS.A.1", "oak_spine"),
        ("BS.A.1", PREPARER),
        ("D-2", PREPARER),
        ("PL.R.1", PREPARER),
    ]
    assert done["generated"]["payload"]["inputs"]["regeneration"]["references"]["kept"] == [
        "BS.A.1"
    ]
