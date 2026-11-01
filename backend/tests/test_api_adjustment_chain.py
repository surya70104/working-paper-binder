"""The adjustment-chain paper the Financial Spine produces (spec 3C "the adjustment chain";
Stage E step E3, D32): one W-ADJ per binder in section W, every adjustment in every status
and the uncorrected schedule exactly as served, references to working papers by exact text,
unmatched names listed as information. Against oak_binder_test with the Spine double. No
area map is needed, so the shipped statutory template is used as it is."""

from __future__ import annotations

import json
import re
from typing import Any

import pytest
from fastapi.testclient import TestClient

from oak_binder.hashing import content_hash
from tests.conftest import PREPARER, act_as, use_spine
from tests.fake_spine import ENGAGEMENT_ID, LOCKED_HASH, LOCKED_VERSION_ID, OPEN_VERSION_ID
from tests.helpers import PARTNER, complete_binder, create_binder, create_paper, full_chain

pytestmark = pytest.mark.db


def link(api: TestClient, binder_id: str, version: Any = LOCKED_VERSION_ID) -> None:
    response = api.patch(
        f"/api/binders/{binder_id}",
        json={"spine_engagement_id": str(ENGAGEMENT_ID), "spine_version_id": str(version)},
    )
    assert response.status_code == 200, response.text


def generate(api: TestClient, binder_id: str, expected: int = 201) -> Any:
    response = api.post(f"/api/binders/{binder_id}/spine-papers/adjustment-chain")
    assert response.status_code == expected, f"{response.status_code} {response.text}"
    return response.json()


def status_of(api: TestClient, binder_id: str) -> dict[str, Any]:
    result: dict[str, Any] = api.get(f"/api/binders/{binder_id}/spine-papers").json()
    return result


def test_the_chain_carries_every_adjustment_and_the_uncorrected_schedule_as_served(
    api: TestClient,
) -> None:
    spine = use_spine(api)
    binder = create_binder(api, report_date="2026-09-30")
    link(api, binder["id"])
    cash = create_paper(api, binder["id"], ref="D-1", section="D", title="Cash and bank")
    create_paper(api, binder["id"], ref="D-90", section="D", title="Looks like D-9 but is not")

    before = status_of(api, binder["id"])["chain"]
    assert before == {
        "ref": "W-ADJ",
        "section": "W",
        "paper_id": None,
        "state": "none",
        "can_generate": True,
        "reason": None,
        "detail": None,
        "recorded_version_id": None,
        "recorded_version_label": None,
    }

    paper = generate(api, binder["id"])
    assert paper["ref"] == "W-ADJ" and paper["section"] == "W"
    assert paper["title"] == "Adjustment chain and uncorrected misstatements"
    assert paper["status"] == "draft" and paper["versions"] == []
    assert paper["generated_by"] == "spine" and paper["generated"]["module"] == "oak_spine"
    assert (
        paper["generated"]["run_id"]
        == f"{binder['id']}/{LOCKED_VERSION_ID}/{LOCKED_HASH}/adjustments"
    )
    assert paper["generated"]["locked_fields"] == [
        "title",
        "section",
        "sa_refs",
        "population_sample",
        "result",
    ]
    assert paper["objective"] is None and paper["procedure"] is None and paper["conclusion"] is None

    block = paper["generated"]["payload"]["spine"]
    assert block["kind"] == "adjustment_chain" and block["area"] is None
    assert block["version_hash"] == LOCKED_HASH and block["lines"] == [] and block["ledgers"] == []
    # Every adjustment, in every status, as served.
    client = spine.client()
    served_adjustments = client.adjustments(LOCKED_VERSION_ID)
    assert [a["adjustment_id"] for a in block["adjustments"]] == [
        a["adjustment_id"] for a in served_adjustments
    ]
    assert [a["status"] for a in block["adjustments"]] == ["accepted", "proposed", "refused"]
    for ours, theirs in zip(block["adjustments"], served_adjustments, strict=True):
        for key in (
            "kind",
            "status",
            "narration",
            "working_paper_ref",
            "finding_ref",
            "proposed_by",
            "proposed_at",
            "decided_by",
            "decided_at",
            "decision_note",
        ):
            assert ours[key] == theirs[key], key
        for our_line, their_line in zip(ours["lines"], theirs["lines"], strict=True):
            assert (our_line["dr"], our_line["cr"], our_line["head_id"]) == (
                their_line["dr"],
                their_line["cr"],
                their_line["head_id"],
            )
    # The uncorrected schedule is the Spine's object, byte for byte.
    assert block["uncorrected"] == json.loads(json.dumps(client.uncorrected(LOCKED_VERSION_ID)))

    # Rendering: every figure in the result is a string the Spine served; nothing is computed.
    served: set[str] = set()

    def collect(value: Any) -> None:
        if isinstance(value, str):
            served.add(value)
        elif isinstance(value, dict):
            for v in value.values():
                collect(v)
        elif isinstance(value, list):
            for v in value:
                collect(v)

    collect(served_adjustments)
    collect(client.uncorrected(LOCKED_VERSION_ID))
    for figure in re.findall(r"\b\d+\.\d\d\b", paper["result"]):
        assert figure in served, figure
    for text in (
        "Unrecorded bank interest",
        "Regroup related-party receivable",
        "Cut-off: March invoice",
        "| accepted |",
        "| proposed |",
        "| refused |",
        "performance_materiality: 250000.00",
        "aggregate: 15000.00",
        "headroom: 235000.00",
        "gate: open",
        "### uncorrected",
        "### unposted_reclassifications",
        "| adj-0003 |",
    ):
        assert text in paper["result"], text
    assert "nil" not in paper["result"].lower()
    assert (
        "3 adjustment(s) served (1 accepted, 1 proposed, 1 refused)" in paper["population_sample"]
    )
    assert "1 uncorrected misstatement(s) listed by the Spine" in paper["population_sample"]

    # Working papers: D-1 matched by exact text; D-9 matches nothing (D-90 is not D-9).
    [xref] = paper["xrefs"]
    assert xref["to_wp"] == cash["id"] and xref["to_ref"] == "D-1" and xref["direction"] == "to"
    assert "| D-1 | paper D-1: Cash and bank |" in paper["result"]
    assert "| D-9 | no paper of this binder with that reference |" in paper["result"]
    assert paper["generated"]["payload"]["inputs"]["working_paper_refs"] == {
        "D-1": "D-1",
        "D-9": None,
    }
    # An unmatched name is information: nothing blocks and nothing is guessed.
    assembly = api.get(f"/api/binders/{binder['id']}/assembly").json()
    assert not [b for b in assembly["blockers"] if b["kind"] == "broken_reference"]

    after = status_of(api, binder["id"])["chain"]
    assert after["state"] == "current" and after["paper_id"] == paper["id"]
    assert (
        after["can_generate"] is False and after["reason"] == "the adjustment chain already exists"
    )
    assert spine.non_get_calls() == []


def test_one_chain_per_binder_and_one_per_version_across_binders(api: TestClient) -> None:
    use_spine(api)
    first = create_binder(api)
    second = create_binder(api)
    link(api, first["id"])
    link(api, second["id"])
    a = generate(api, first["id"])
    b = generate(api, second["id"])
    assert a["ref"] == b["ref"] == "W-ADJ" and a["id"] != b["id"]
    assert a["generated"]["run_id"] != b["generated"]["run_id"]
    for _ in range(2):
        refused = generate(api, first["id"], 409)
        assert "already received as paper W-ADJ" in refused["detail"]
        assert "one paper per run" in refused["detail"]
    # A hand-made paper holding W-ADJ is refused as for any paper (spec 3B).
    third = create_binder(api)
    link(api, third["id"])
    create_paper(api, third["id"], ref="W-ADJ", section="W", title="Hand-made")
    assert "already used" in generate(api, third["id"], 409)["detail"]


def test_the_chain_is_refused_by_name_when_it_cannot_be_generated(api: TestClient) -> None:
    spine = use_spine(api)
    unlinked = create_binder(api)
    assert "not linked" in generate(api, unlinked["id"], 409)["detail"]
    assert status_of(api, unlinked["id"])["chain"]["can_generate"] is False
    link(api, unlinked["id"], OPEN_VERSION_ID)
    assert "is not locked" in generate(api, unlinked["id"], 409)["detail"]
    linked = create_binder(api)
    link(api, linked["id"])
    spine.fail_with = 503
    assert "could not answer" in generate(api, linked["id"], 503)["detail"]
    spine.fail_with = None
    assembled = complete_binder(api)
    link(api, assembled["id"])
    act_as(api, PARTNER)
    assert api.post(f"/api/binders/{assembled['id']}/assemble").status_code == 200
    assert "the binder is assembled" in generate(api, assembled["id"], 409)["detail"]
    act_as(api, PREPARER)
    assert all(not s["papers"] for s in api.get(f"/api/binders/{linked['id']}").json()["sections"])


def test_people_sign_the_chain_off_and_the_provenance_travels(api: TestClient) -> None:
    use_spine(api)
    binder = create_binder(api)
    link(api, binder["id"])
    paper = generate(api, binder["id"])
    refused = api.patch(f"/api/papers/{paper['id']}", json={"result": "retyped"})
    assert refused.status_code == 422 and "came from oak_spine (spine)" in refused.json()["detail"]
    assert (
        api.patch(
            f"/api/papers/{paper['id']}",
            json={"objective": "Consider the uncorrected misstatements."},
        ).status_code
        == 200
    )
    assert (
        api.patch(
            f"/api/papers/{paper['id']}",
            json={"conclusion": "Below performance materiality; no further work."},
        ).status_code
        == 200
    )
    signed = full_chain(api, paper["id"])
    assert signed["status"] == "signed_off" and signed["versions"][2]["signed_off_by"] == PARTNER
    for version in signed["versions"]:
        body = version["body"]
        assert body["generated"]["payload"]["spine"]["kind"] == "adjustment_chain"
        assert body["generated"]["payload"]["spine"]["uncorrected"]["aggregate"] == "15000.00"
        assert version["content_hash"] == content_hash(body)
    act_as(api, PREPARER)


def test_a_chain_with_no_adjustments_says_so(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tests.fake_spine as fake

    use_spine(api)
    monkeypatch.setattr(fake, "adjustments_record", lambda version_id: [])
    monkeypatch.setattr(
        fake,
        "uncorrected_record",
        lambda version_id, locked: {
            "version_id": str(version_id),
            "is_locked": locked,
            "uncorrected": [],
            "aggregate": "0.00",
            "gate": "undetermined",
            "performance_materiality": None,
        },
    )
    binder = create_binder(api)
    link(api, binder["id"])
    paper = generate(api, binder["id"])
    assert paper["generated"]["payload"]["spine"]["adjustments"] == []
    assert "The Spine lists no adjustment on this version." in paper["result"]
    assert "No adjustment names a working paper." in paper["result"]
    assert "performance_materiality: no figure served" in paper["result"]
    assert "aggregate: 0.00" in paper["result"]  # served as "0.00": quoted as served
    assert paper["xrefs"] == []
    assert "0 adjustment(s) served (none)" in paper["population_sample"]
