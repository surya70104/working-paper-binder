"""Lead schedules the Financial Spine produces (spec 3A, 3C; Stage E step E2, D32), against
oak_binder_test with the Spine double. The shipped templates carry no area map, so these
tests give the statutory template a test map (through the service's template lookup) that
assigns the double's heads to areas D–H; nothing in the shipped files changes."""

from __future__ import annotations

import copy
import json
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from oak_binder.hashing import content_hash
from oak_binder.services import spine_papers
from oak_binder.services.templates import TEMPLATES_DIR, parse_template
from tests.conftest import PREPARER, act_as, use_spine
from tests.fake_spine import ENGAGEMENT_ID, LOCKED_HASH, LOCKED_VERSION_ID, OPEN_VERSION_ID
from tests.helpers import PARTNER, complete_binder, create_binder, create_paper, full_chain

pytestmark = pytest.mark.db

# The test map: every mappable head of the double's tree except PL.R.1 (left unassigned on
# purpose); E covers BS.A.2's branch, which includes X.ODD (under BS.A.2 by its parent field)
# and BS.A.2.1 (a ledger at "0.00"); F covers PL.E.1, a head with no ledger entry at all.
TEST_AREAS: dict[str, dict[str, Any]] = {
    "D": {"heads": ["BS.A.1"], "objective": "Agree cash and cash equivalents to the Spine."},
    "E": {"heads": ["BS.A.2"]},
    "F": {"heads": ["PL.E.1"]},
    "G": {"heads": ["BS.L.1"]},
}


def use_area_map(
    monkeypatch: pytest.MonkeyPatch, areas: dict[str, Any] | None = TEST_AREAS
) -> None:
    raw = json.loads((TEMPLATES_DIR / "statutory.json").read_text(encoding="utf-8"))
    raw = copy.deepcopy(raw)
    raw["areas"] = areas or {}
    template = parse_template("statutory", raw)
    monkeypatch.setattr(spine_papers, "load_template", lambda name: template)


def link(api: TestClient, binder_id: str, version: uuid.UUID = LOCKED_VERSION_ID) -> None:
    response = api.patch(
        f"/api/binders/{binder_id}",
        json={"spine_engagement_id": str(ENGAGEMENT_ID), "spine_version_id": str(version)},
    )
    assert response.status_code == 200, response.text


def generate(api: TestClient, binder_id: str, areas: list[str] | None, expected: int = 201) -> Any:
    response = api.post(
        f"/api/binders/{binder_id}/spine-papers/lead-schedules", json={"areas": areas}
    )
    assert response.status_code == expected, f"{response.status_code} {response.text}"
    return response.json()


def status_of(api: TestClient, binder_id: str) -> dict[str, Any]:
    result: dict[str, Any] = api.get(f"/api/binders/{binder_id}/spine-papers").json()
    return result


def test_lead_schedules_are_generated_per_mapped_area_from_the_locked_version(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    spine = use_spine(api)
    use_area_map(monkeypatch)
    binder = create_binder(api, report_date="2026-09-30")
    link(api, binder["id"])

    before = status_of(api, binder["id"])
    assert before["can_generate"] is True and before["version_hash"] == LOCKED_HASH
    assert {a["code"]: a["mapped"] for a in before["areas"] if a["code"] in "DEFGH"} == {
        "D": True,
        "E": True,
        "F": True,
        "G": True,
        "H": False,
    }
    assert before["unassigned_heads"] == ["PL.R.1"]

    papers = generate(api, binder["id"], None)  # every mapped area without a lead schedule
    assert [p["ref"] for p in papers] == ["D-L", "E-L", "F-L", "G-L"]
    assert [p["section"] for p in papers] == ["D", "E", "F", "G"]
    for paper in papers:
        assert paper["status"] == "draft" and paper["versions"] == []
        assert paper["generated_by"] == "spine" and paper["generated"]["module"] == "oak_spine"
        assert paper["generated"]["received_by"] == PREPARER
        assert paper["title"].startswith("Lead schedule: Financial statement area")
        assert paper["conclusion"] is None and paper["procedure"] is None
        # Figures are the Spine's, not the Binder's: objective and procedure stay a person's.
        assert paper["generated"]["locked_fields"] == [
            "title",
            "section",
            "sa_refs",
            "population_sample",
            "result",
        ]
        block = paper["generated"]["payload"]["spine"]
        assert block["kind"] == "lead_schedule" and block["version_hash"] == LOCKED_HASH
        assert block["balances_hash"] == LOCKED_HASH and block["tree_version"] == 3
        assert (
            paper["generated"]["run_id"]
            == f"{binder['id']}/{LOCKED_VERSION_ID}/{LOCKED_HASH}/{paper['section']}"
        )

    d, e, f, g = papers
    # D: approved template wording inserted, one line, two ledgers, the accepted adjustment.
    assert d["objective"] == "Agree cash and cash equivalents to the Spine."
    block = d["generated"]["payload"]["spine"]
    assert [ln["head_id"] for ln in block["lines"]] == ["BS.A.1"]
    assert block["lines"][0]["current"] == "1250000.00" and block["lines"][0]["prior"] is None
    assert [r["ledger_key"] for r in block["ledgers"]] == ["hdfc-current", "cash-in-hand"]
    assert (
        block["ledgers"][0]["corrections"] == "50000.00"
        and block["ledgers"][1]["adjusted"] == "0.00"
    )
    assert block["head_totals"] == [
        {
            "head_id": "BS.A.1",
            "ledgers": 2,
            "unadjusted": "1200000.00",
            "adjusted": "1250000.00",
            "prior_closing": "912000.00",
        }
    ]
    assert block["heads_without_ledgers"] == []
    assert [a["adjustment_id"] for a in block["adjustments"]] == ["adj-0001"]
    for figure in ("1250000.00", "1200000.00", "50000.00", "912000.00", "900000.00", "12000.00"):
        assert figure in d["result"]
    assert "HDFC Bank current account" in d["result"] and "adj-0001" in d["result"]
    assert "2 ledger row(s) served under 1 head(s) of area D" in d["population_sample"]
    # The reference to the FS line makes D-L the line's lead schedule (spec 3E).
    [xref] = d["xrefs"]
    assert xref["to_fs_line"] == "BS.A.1" and xref["checked"] and xref["broken"] is None
    assert xref["to_fs_line_label"] == "Cash and cash equivalents"

    # E: X.ODD is covered through its parent field; BS.A.2.1 has a ledger at "0.00", quoted as
    # served; X.ODD has none and the paper says so; no presentation line exists for the branch.
    block = e["generated"]["payload"]["spine"]
    assert block["lines"] == [] and e["xrefs"] == []
    assert [r["head_id"] for r in block["ledgers"]] == ["BS.A.2.1"]
    assert (
        block["ledgers"][0]["adjusted"] == "0.00" and block["ledgers"][0]["prior_closing"] == "0.00"
    )
    assert block["heads_without_ledgers"] == ["X.ODD"]
    assert [a["adjustment_id"] for a in block["adjustments"]] == ["adj-0002", "adj-0003"]
    assert "| Customer A |" in e["result"] and "| 0.00 |" in e["result"]
    assert (
        "list no ledger under this head; no presentation line served for this head" in e["result"]
    )
    assert "serves no financial statement line under this area's heads" in e["result"]
    assert "nil" not in e["result"].lower()

    # F: a head with no ledger entry and no served figure; nothing is asserted as a figure.
    block = f["generated"]["payload"]["spine"]
    assert block["ledgers"] == [] and block["head_totals"] == [] and block["lines"] == []
    assert block["heads_without_ledgers"] == ["PL.E.1"] and block["adjustments"] == []
    assert "The balances of Spine version Final" in f["result"]
    assert (
        "list no ledger under this head; no presentation line served for this head" in f["result"]
    )
    assert "The Spine lists no adjustment with a line under this area's heads." in f["result"]
    assert "0 ledger row(s) served under 0 head(s) of area F" in f["population_sample"]
    assert "0.00" not in f["result"] and "nil" not in f["result"].lower()

    # G: trade payables, one ledger, one line, no adjustment.
    assert [ln["head_id"] for ln in g["generated"]["payload"]["spine"]["lines"]] == ["BS.L.1"]
    assert "480000.00" in g["result"] and "410000.00" in g["result"]

    after = status_of(api, binder["id"])
    by_code = {a["code"]: a for a in after["areas"]}
    assert by_code["D"]["state"] == "current" and by_code["D"]["ref"] == "D-L"
    assert (
        by_code["H"]["state"] == "none"
        and by_code["H"]["detail"] == "no Schedule III heads in the area map"
    )
    assert spine.non_get_calls() == []


def test_every_figure_in_the_paper_is_a_string_the_spine_served(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    spine = use_spine(api)
    use_area_map(monkeypatch)
    binder = create_binder(api)
    link(api, binder["id"])
    [paper] = generate(api, binder["id"], ["D"])
    client = spine.client()
    balances = client.balances(LOCKED_VERSION_ID)
    for ledger in balances["ledgers"]:
        if ledger["head_id"] != "BS.A.1":
            continue
        for key in ("unadjusted", "reclass", "corrections", "adjusted", "prior_closing"):
            assert ledger[key] in paper["result"], (ledger["ledger_key"], key)
    for group in balances["groups"]:
        if group["head_id"] == "BS.A.1":
            totals = (
                f"unadjusted {group['unadjusted']}; adjusted {group['adjusted']}; "
                f"prior {group['prior_closing']}"
            )
            assert totals in paper["result"]
    # No arithmetic: the result never shows a figure the Spine did not serve under this head.
    served = {v for ledger in balances["ledgers"] for v in ledger.values() if isinstance(v, str)}
    served |= {v for g in balances["groups"] for v in g.values() if isinstance(v, str)}
    import re

    for figure in re.findall(r"\b\d+\.\d\d\b", paper["result"]):
        assert figure in served, figure


def test_the_map_shows_the_generated_paper_as_the_lines_lead_schedule(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_spine(api)
    use_area_map(monkeypatch)
    binder = create_binder(api)
    link(api, binder["id"])
    [lead] = generate(api, binder["id"], ["D"])
    cash = create_paper(api, binder["id"], ref="D-1", section="D", title="Bank reconciliations")
    api.post(
        f"/api/papers/{cash['id']}/xrefs", json={"to_wp": lead["id"], "direction": "to"}
    ).raise_for_status()
    m = api.get(f"/api/binders/{binder['id']}/xref-map").json()
    [line] = m["lines"]
    assert line["head_id"] == "BS.A.1" and line["known"] is True
    [node] = line["papers"]
    assert node["ref"] == "D-L" and node["role"] == "lead_schedule"
    assert [p["ref"] for p in node["papers"]] == ["D-1"]


def test_the_chain_signs_a_lead_schedule_off_with_people_and_the_provenance_travels(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_spine(api)
    use_area_map(monkeypatch)
    binder = create_binder(api)
    link(api, binder["id"])
    [paper] = generate(api, binder["id"], ["G"])
    # A person writes the procedure and the conclusion; the Spine's fields are locked.
    assert (
        api.patch(
            f"/api/papers/{paper['id']}", json={"procedure": "Agreed to the Spine."}
        ).status_code
        == 200
    )
    refused = api.patch(f"/api/papers/{paper['id']}", json={"result": "retyped"})
    assert refused.status_code == 422 and "came from oak_spine (spine)" in refused.json()["detail"]
    assert (
        api.patch(f"/api/papers/{paper['id']}", json={"conclusion": "Payables agree."}).status_code
        == 200
    )
    signed = full_chain(api, paper["id"])
    assert signed["status"] == "signed_off" and signed["versions"][0]["prepared_by"] == PREPARER
    assert signed["versions"][2]["signed_off_by"] == PARTNER
    for version in signed["versions"]:
        assert version["body"]["generated"]["payload"]["spine"]["version_hash"] == LOCKED_HASH
        assert version["content_hash"] == content_hash(version["body"])
    act_as(api, PREPARER)


def test_generation_is_refused_by_name_when_it_cannot_be_done(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    spine = use_spine(api)
    # Shipped template: no area map, so one is derived from the tree (D38) and nothing refuses.
    binder = create_binder(api)
    link(api, binder["id"])
    status = status_of(api, binder["id"])
    assert status["can_generate"] is True and status["map_source"] == "derived"

    use_area_map(monkeypatch)
    # An area the map does not cover.
    assert "area H has no Schedule III heads" in generate(api, binder["id"], ["H"], 422)["detail"]
    assert (
        "'Q9' is not a financial statement area"
        in generate(api, binder["id"], ["Q9"], 422)["detail"]
    )
    assert "named twice" in generate(api, binder["id"], ["D", "D"], 422)["detail"]
    assert "name at least one area" in generate(api, binder["id"], [], 422)["detail"]
    # Unlinked, unlocked, unreachable.
    unlinked = create_binder(api)
    assert "not linked" in generate(api, unlinked["id"], ["D"], 409)["detail"]
    assert status_of(api, unlinked["id"])["can_generate"] is False
    link(api, unlinked["id"], OPEN_VERSION_ID)
    refused = generate(api, unlinked["id"], ["D"], 409)
    assert "is not locked" in refused["detail"] and "decision 1" in refused["detail"]
    spine.fail_with = 503
    assert "could not answer" in generate(api, binder["id"], ["D"], 503)["detail"]
    spine.fail_with = None
    # A map refused against the tree.
    use_area_map(monkeypatch, {"D": {"heads": ["BS.A"]}, "E": {"heads": ["BS.A.2"]}})
    refused = generate(api, binder["id"], ["D"], 422)
    assert "both cover heads" in refused["detail"]
    assert "both cover heads" in status_of(api, binder["id"])["reason"]
    # Nothing was filed by any refusal.
    assert all(not s["papers"] for s in api.get(f"/api/binders/{binder['id']}").json()["sections"])


def test_one_paper_per_run_and_several_binders_on_one_version(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_spine(api)
    use_area_map(monkeypatch)
    first = create_binder(api)
    second = create_binder(api)
    link(api, first["id"])
    link(api, second["id"])
    [a] = generate(api, first["id"], ["D"])
    [b] = generate(api, second["id"], ["D"])  # the same version and area, another binder
    assert a["generated"]["run_id"] != b["generated"]["run_id"]
    assert a["id"] != b["id"] and a["ref"] == b["ref"] == "D-L"
    # A repeat on the same unchanged version is refused, naming the existing paper, twice over.
    for _ in range(2):
        refused = generate(api, first["id"], ["D"], 409)
        assert "already received as paper D-L" in refused["detail"]
        assert "one paper per run" in refused["detail"]
    # "All mapped areas" fills in the rest and then has nothing left to do.
    rest = generate(api, first["id"], None)
    assert [p["ref"] for p in rest] == ["E-L", "F-L", "G-L"]
    refused = generate(api, first["id"], None, 409)
    assert "every mapped area already has its lead schedule" in refused["detail"]
    # A hand-made paper holding the reference is refused as for any paper (spec 3B).
    third = create_binder(api)
    link(api, third["id"])
    create_paper(api, third["id"], ref="D-L", section="D", title="Hand-made")
    assert "already used" in generate(api, third["id"], ["D"], 409)["detail"]


def test_no_generation_after_assembly(api: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    use_spine(api)
    use_area_map(monkeypatch)
    binder = complete_binder(api)
    link(api, binder["id"])
    act_as(api, PARTNER)
    assert api.post(f"/api/binders/{binder['id']}/assemble").status_code == 200
    refused = generate(api, binder["id"], ["D"], 409)
    assert "the binder is assembled" in refused["detail"]
    assert status_of(api, binder["id"])["can_generate"] is False
    act_as(api, "quality.reviewer@firm")
    assert api.get(f"/api/binders/{binder['id']}/spine-papers").status_code == 200
    rows = api.get(f"/api/binders/{binder['id']}/assembly").json()["access"]
    assert [r["action"] for r in rows if r["user"] == "quality.reviewer@firm"][0] == "Spine papers"
    act_as(api, PREPARER)


def test_without_a_template_map_areas_are_derived_from_the_spine_tree(api: TestClient) -> None:
    """D38: the shipped templates carry no map; the Spine's tree gives one area per
    statement-level head group, named as the Spine names it, and lead schedules generate."""
    use_spine(api)
    binder = create_binder(api, report_date="2026-09-30")
    link(api, binder["id"])
    status = status_of(api, binder["id"])
    assert status["can_generate"] is True and status["reason"] is None
    assert status["map_source"] == "derived" and status["beyond_letters"] == []
    assert status["unassigned_heads"] == [] and status["map_problems"] == []
    by_code = {a["code"]: a for a in status["areas"]}
    assert {c: by_code[c]["mapped"] for c in "DEFGH"} == {
        "D": True,
        "E": True,
        "F": True,
        "G": True,
        "H": False,
    }
    assert [by_code[c]["name"] for c in "DEFG"] == ["Assets", "Liabilities", "Revenue", "Expenses"]
    assert by_code["D"]["listed_heads"] == ["BS.A"]
    assert by_code["H"]["name"] == "Financial statement area H"

    papers = generate(api, binder["id"], None)
    assert [p["ref"] for p in papers] == ["D-L", "E-L", "F-L", "G-L"]
    assert [p["title"] for p in papers] == [
        "Lead schedule: Assets",
        "Lead schedule: Liabilities",
        "Lead schedule: Revenue",
        "Lead schedule: Expenses",
    ]
    assert all(p["objective"] is None and p["procedure"] is None for p in papers)
    inputs = papers[0]["generated"]["payload"]["inputs"]
    assert inputs["area_map_source"] == "derived" and inputs["listed_heads"] == ["BS.A"]
    assert set(inputs["covered_heads"]) == {"BS.A", "BS.A.1", "BS.A.2", "X.ODD", "BS.A.2.1"}
    after = status_of(api, binder["id"])
    assert {a["code"]: a["state"] for a in after["areas"] if a["mapped"]} == {
        c: "current" for c in "DEFG"
    }
    refused = generate(api, binder["id"], ["H"], 422)
    assert "map derived from the Spine's tree" in refused["detail"]
