"""Generated-paper intake (spec 3C, 7, 8.8; Pass 2 Stage D, D31), against oak_binder_test.

The four fixtures under tests/fixtures/generated are the contract's worked examples, one per
module source. Materiality, Sampling and Analytical Review are accepted and filed as drafts
with their provenance; WorkMind is validated in full and then refused until the module
exists (decision 6); the Spine's papers are Stage E.
"""

from __future__ import annotations

import copy
import io
import json
import uuid
import zipfile
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from oak_binder.config import Settings
from oak_binder.hashing import content_hash
from tests.conftest import PREPARER, REVIEWER, act_as, use_spine, use_workmind
from tests.fake_spine import ENGAGEMENT_ID, LOCKED_VERSION_ID, OPEN_VERSION_ID
from tests.fake_workmind import PROPOSED_RUN, REFUSED_RUN
from tests.fake_workmind import TOKEN as WORKMIND_TOKEN
from tests.helpers import (
    PARTNER,
    complete_binder,
    create_binder,
    full_chain,
    generated_fixture,
    step,
)

pytestmark = pytest.mark.db

FIXTURES = Path(__file__).parent / "fixtures" / "generated"


def fixture(source: str) -> dict[str, Any]:
    return generated_fixture(source)


def deliver(api: TestClient, binder_id: str, body: dict[str, Any], expected: int = 201) -> Any:
    response = api.post(f"/api/binders/{binder_id}/generated-papers", json=body)
    assert response.status_code == expected, f"{response.status_code} {response.text}"
    return response.json()


def link(api: TestClient, binder_id: str, version: uuid.UUID = LOCKED_VERSION_ID) -> None:
    response = api.patch(
        f"/api/binders/{binder_id}",
        json={"spine_engagement_id": str(ENGAGEMENT_ID), "spine_version_id": str(version)},
    )
    assert response.status_code == 200, response.text


def settings_of(api: TestClient) -> Settings:
    settings: Settings = cast(FastAPI, api.app).state.settings
    return settings


def detail(payload: Any) -> str:
    """FastAPI renders pydantic errors as a list; the Binder's own errors as a string."""
    return (
        json.dumps(payload["detail"])
        if not isinstance(payload["detail"], str)
        else payload["detail"]
    )


# --- the three sources that are accepted -------------------------------------------------------


def test_the_three_module_fixtures_arrive_as_drafts_with_their_provenance(api: TestClient) -> None:
    use_spine(api)
    binder = create_binder(api, report_date="2026-09-30")
    link(api, binder["id"])
    for source in ("materiality", "sampling", "analytical_review"):
        body = fixture(source)
        paper = deliver(api, binder["id"], body)
        assert paper["status"] == "draft" and paper["current_version"] is None  # decision 1
        assert paper["versions"] == []
        assert paper["generated_by"] == source
        gen = paper["generated"]
        assert gen["source"] == source and gen["module"] == body["generated"]["module"]
        assert gen["run_id"] == body["generated"]["run_id"]
        assert gen["received_by"] == PREPARER
        assert gen["payload"]["inputs"] == body["generated"]["inputs"]
        assert gen["payload"]["citations"] == body["generated"]["citations"]
        assert gen["payload"][source] == json.loads(json.dumps(body["generated"][source]))
        assert gen["locked_fields"] == [
            "title",
            "section",
            "sa_refs",
            "objective",
            "procedure",
            "population_sample",
            "result",
        ]
        # The module's fields are exactly what arrived: nothing retyped (spec 3C).
        for name, value in body["paper"].items():
            assert paper[name] == value, name
        assert api.get(f"/api/papers/{paper['id']}/generation").json()["source"] == source
    # Only the memo takes Spine figures; the binder is linked, so they were verified.
    index = api.get(f"/api/binders/{binder['id']}").json()
    generated = {p["ref"]: p["generated_by"] for s in index["sections"] for p in s["papers"]}
    assert generated == {"C-1": "materiality", "D-3": "sampling", "D-4": "analytical_review"}
    memo = next(p for s in index["sections"] for p in s["papers"] if p["ref"] == "C-1")
    assert api.get(f"/api/papers/{memo['id']}").json()["generated"]["spine_figures_check"] == (
        "verified"
    )


def test_provenance_travels_in_every_version_body_and_its_hash(api: TestClient) -> None:
    binder = create_binder(api)
    paper = deliver(api, binder["id"], fixture("sampling"))
    signed = full_chain(api, paper["id"])
    bodies = [v["body"] for v in signed["versions"]]
    assert len(bodies) == 3 and all("generated" in b for b in bodies)
    block = bodies[0]["generated"]
    assert block["source"] == "sampling" and block["received_by"] == PREPARER
    assert block["payload"]["sampling"] == {
        "formula": "interval = population_value / sample_size",
        "seed": 20261031,
    }
    assert block["payload"]["inputs"]["sample_size"] == 60
    assert block["content_hash_at_intake"] == signed["generated"]["content_hash_at_intake"]
    # The content hash is over the whole body, provenance included (spec 8.5 reproducibility).
    for version in signed["versions"]:
        assert version["content_hash"] == content_hash(version["body"])
    # A person prepared, reviewed and signed: the module is nowhere in the sign-off chain.
    assert signed["versions"][0]["prepared_by"] == PREPARER
    assert signed["versions"][2]["signed_off_by"] == PARTNER
    act_as(api, PREPARER)


def test_hand_made_papers_are_untouched_by_the_feature(api: TestClient) -> None:
    binder = create_binder(api)
    from tests.helpers import create_paper

    paper = create_paper(api, binder["id"])
    assert paper["generated"] is None and paper["generated_by"] is None
    prepared = step(api, paper["id"], "prepare")
    assert "generated" not in prepared["versions"][0]["body"]
    assert api.get(f"/api/papers/{paper['id']}/generation").status_code == 404
    index = api.get(f"/api/binders/{binder['id']}").json()
    assert all(p["generated_by"] is None for s in index["sections"] for p in s["papers"])


# --- per-source rules -----------------------------------------------------------------------------


def test_materiality_figures_are_checked_against_the_linked_spine_version(api: TestClient) -> None:
    use_spine(api)
    linked = create_binder(api)
    link(api, linked["id"], OPEN_VERSION_ID)  # linked to the OPEN version
    body = fixture("materiality")  # its figures come from the LOCKED version
    refused = deliver(api, linked["id"], body, 422)
    assert (
        "come from Spine version" in refused["detail"] and "linked to version" in refused["detail"]
    )
    body["generated"]["materiality"]["spine_figures"]["version_id"] = str(OPEN_VERSION_ID)
    assert deliver(api, linked["id"], body)["generated"]["spine_figures_check"] == "verified"

    unlinked = create_binder(api)
    elsewhere = fixture("materiality")
    elsewhere["generated"]["run_id"] = "materiality-run-example-002"  # unique per source
    kept = deliver(api, unlinked["id"], elsewhere)
    assert kept["generated"]["spine_figures_check"] == "not_checked"  # decision 5
    assert kept["generated"]["payload"]["materiality"]["spine_figures"]["figures"]["PL.R.1"] == (
        "9800000.00"
    )

    for missing in ("benchmark", "band", "spine_figures"):
        body = fixture("materiality")
        del body["generated"]["materiality"][missing]
        assert missing in detail(deliver(api, unlinked["id"], body, 422))
    body = fixture("materiality")
    body["generated"]["materiality"]["band"] = {}
    assert "band must not be empty" in detail(deliver(api, unlinked["id"], body, 422))
    body = fixture("materiality")
    body["generated"]["materiality"]["spine_figures"]["figures"] = []
    assert "figures must not be empty" in detail(deliver(api, unlinked["id"], body, 422))


def test_a_sampling_paper_carries_its_formula_and_seed_printed_on_it(api: TestClient) -> None:
    binder = create_binder(api)
    body = fixture("sampling")
    body["paper"]["population_sample"] = body["paper"]["population_sample"].replace(
        "Seed: 20261031.", "Seed: on file."
    )
    refused = deliver(api, binder["id"], body, 422)
    assert "seed printed on it" in refused["detail"] and "'20261031'" in refused["detail"]

    body = fixture("sampling")
    body["generated"]["sampling"]["formula"] = "n = (BV x CF) / TM"  # not what the paper says
    refused = deliver(api, binder["id"], body, 422)
    assert "formula printed on it" in refused["detail"]

    body = fixture("sampling")
    del body["generated"]["sampling"]["seed"]
    assert "seed" in detail(deliver(api, binder["id"], body, 422))
    body = fixture("sampling")
    body["generated"]["sampling"]["formula"] = "   "
    assert "formula must not be blank" in detail(deliver(api, binder["id"], body, 422))
    # A seed given as text is matched as text.
    body = fixture("sampling")
    body["generated"]["sampling"]["seed"] = "20261031"
    assert (
        deliver(api, binder["id"], body)["generated"]["payload"]["sampling"]["seed"] == "20261031"
    )


def test_analytical_review_needs_both_periods_and_thresholds(api: TestClient) -> None:
    binder = create_binder(api)
    body = fixture("analytical_review")
    body["generated"]["analytical_review"]["periods"]["prior"] = "FY2025-26"
    assert "must differ" in detail(deliver(api, binder["id"], body, 422))
    body = fixture("analytical_review")
    body["generated"]["analytical_review"]["thresholds"] = {}
    assert "thresholds must not be empty" in detail(deliver(api, binder["id"], body, 422))
    body = fixture("analytical_review")
    del body["generated"]["analytical_review"]["periods"]
    assert "periods" in detail(deliver(api, binder["id"], body, 422))
    assert deliver(api, binder["id"], fixture("analytical_review"))["generated_by"] == (
        "analytical_review"
    )


def test_the_block_must_match_the_source_and_carry_no_unknown_keys(api: TestClient) -> None:
    binder = create_binder(api)
    body = fixture("sampling")
    body["generated"]["analytical_review"] = fixture("analytical_review")["generated"][
        "analytical_review"
    ]
    assert "carries no analytical_review block" in detail(deliver(api, binder["id"], body, 422))
    body = fixture("sampling")
    del body["generated"]["sampling"]
    assert "needs its sampling block" in detail(deliver(api, binder["id"], body, 422))
    body = fixture("sampling")
    body["generated"]["sampling"]["confidence"] = 0.95  # not in the contract: strict (decision 11)
    assert "confidence" in detail(deliver(api, binder["id"], body, 422))
    body = fixture("sampling")
    body["generated"]["inputs"] = {}
    assert "inputs must not be empty" in detail(deliver(api, binder["id"], body, 422))
    body = fixture("sampling")
    body["generated"]["citations"] = []
    assert "citations must not be empty" in detail(deliver(api, binder["id"], body, 422))
    body = fixture("sampling")
    body["generated"]["module"] = "  "
    assert "module must not be blank" in detail(deliver(api, binder["id"], body, 422))
    body = fixture("sampling")
    body["generated"]["source"] = "spreadsheet"
    assert "source" in detail(deliver(api, binder["id"], body, 422))


def test_a_workmind_paper_is_refused_until_a_workmind_is_configured_to_verify_the_run(
    api: TestClient,
) -> None:
    """Spec 3C: one paper per *accepted* run. Without a WorkMind to read the run back from,
    acceptance cannot be verified, so the delivery is refused (503) and nothing is filed; the
    contract itself is enforced first (D31, D37)."""
    binder = create_binder(api)
    body = fixture("workmind")
    refused = deliver(api, binder["id"], body, 503)
    assert "no WorkMind is configured (OAK_WORKMIND_URL)" in refused["detail"]
    assert "cannot be verified as accepted" in refused["detail"]
    body = fixture("workmind")
    del body["generated"]["run_id"]
    assert "run_id is required" in detail(deliver(api, binder["id"], body, 422))
    body = fixture("workmind")
    body["generated"]["workmind"]["source_row_citations"] = []
    assert "source_row_citations" in detail(deliver(api, binder["id"], body, 422))
    body = fixture("workmind")
    body["generated"]["workmind"]["source_row_citations"][0] = {"source": "x"}
    assert "row" in detail(deliver(api, binder["id"], body, 422))
    body = fixture("workmind")
    body["paper"]["conclusion"] = "Receivables are recoverable."
    refused = deliver(api, binder["id"], body, 422)
    assert "conclusions are not drafted automatically (spec 7)" in refused["detail"]
    index = api.get(f"/api/binders/{binder['id']}").json()
    assert all(not s["papers"] for s in index["sections"])


def test_a_workmind_paper_is_filed_only_for_a_run_workmind_reports_as_accepted(
    api: TestClient,
) -> None:
    """With a WorkMind configured (here the local double), the run is read back: an accepted run
    becomes a draft paper whose provenance records the verification; a proposed, refused or
    unknown run files nothing (D37)."""
    workmind = use_workmind(api)
    binder = create_binder(api)
    body = fixture("workmind")
    run_id = body["generated"]["run_id"]
    paper = deliver(api, binder["id"], body, 201)
    assert paper["status"] == "draft" and paper["conclusion"] is None
    assert paper["generated_by"] == "workmind"
    generation = api.get(f"/api/papers/{paper['id']}/generation").json()
    verification = generation["run_verification"]
    assert verification["checked_at"]
    assert {k: v for k, v in verification.items() if k != "checked_at"} == {
        "module": "workmind",
        "endpoint": f"/api/runs/{run_id}",
        "status": "accepted",
        "accepted_by": "manager@firm",
        "accepted_at": "2026-10-31T12:30:00+05:30",
    }
    assert [c.path for c in workmind.calls] == [f"/api/runs/{run_id}"]
    assert workmind.non_get_calls() == []
    # The verification travels in every version's provenance block (spec 3C; D31).
    act_as(api, PREPARER)
    step(api, paper["id"], "prepare")
    produced = api.get(f"/api/papers/{paper['id']}").json()
    assert produced["versions"][-1]["body"]["generated"]["run_verification"]["status"] == "accepted"
    # One paper per run: the same run again is refused.
    again = deliver(api, binder["id"], body, 409)
    assert "was already received" in again["detail"]
    # A proposed, a refused and an unknown run file nothing.
    for run_id, code, text in (
        (PROPOSED_RUN, 409, "is 'proposed', not accepted"),
        (REFUSED_RUN, 409, "is 'refused', not accepted"),
        ("wm-run-nowhere", 404, "WorkMind has no run 'wm-run-nowhere'"),
    ):
        body = fixture("workmind")
        body["paper"]["ref"] = "D-6"
        body["generated"]["run_id"] = run_id
        refused = deliver(api, binder["id"], body, code)
        assert text in refused["detail"], refused
    index = api.get(f"/api/binders/{binder['id']}").json()
    assert {p["ref"] for s in index["sections"] for p in s["papers"]} == {"D-5"}


def test_a_workmind_outage_or_bad_answer_refuses_the_delivery_and_files_nothing(
    api: TestClient,
) -> None:
    workmind = use_workmind(api)
    binder = create_binder(api)
    workmind.fail_with = 503
    refused = deliver(api, binder["id"], fixture("workmind"), 503)
    assert "WorkMind answered HTTP 503" in refused["detail"]
    workmind.fail_with = None
    workmind.time_out = True
    assert "did not answer in time" in detail(deliver(api, binder["id"], fixture("workmind"), 503))
    workmind.time_out = False
    workmind.non_json = True
    assert "unexpected answer" in detail(deliver(api, binder["id"], fixture("workmind"), 503))
    workmind.non_json = False
    workmind.require_token = True
    assert "refused the Binder's credential" in detail(
        deliver(api, binder["id"], fixture("workmind"), 503)
    )
    index = api.get(f"/api/binders/{binder['id']}").json()
    assert all(not s["papers"] for s in index["sections"])
    # With the credential configured, the same delivery is filed.
    cast(FastAPI, api.app).state.workmind_client = workmind.client(WORKMIND_TOKEN)
    assert deliver(api, binder["id"], fixture("workmind"), 201)["generated_by"] == "workmind"
    assert workmind.calls[-1].headers.get("authorization") == f"Bearer {WORKMIND_TOKEN}"


def test_spine_papers_never_arrive_through_the_intake_endpoint(api: TestClient) -> None:
    """Stage E (D32): the Binder builds Spine papers itself; a well-formed delivery with
    source 'spine' is refused by name, and a malformed one by the contract first."""
    from tests.test_spine_block import LEAD_SCHEDULE

    binder = create_binder(api)
    body = fixture("sampling")
    body["generated"]["source"] = "spine"
    del body["generated"]["sampling"]
    assert "needs its spine block" in detail(deliver(api, binder["id"], body, 422))
    body["generated"]["spine"] = LEAD_SCHEDULE
    refused = deliver(api, binder["id"], body, 422)
    assert "Binder's own Spine-papers action, not this endpoint" in refused["detail"]
    assert all(not s["papers"] for s in api.get(f"/api/binders/{binder['id']}").json()["sections"])


def test_one_paper_per_run_within_a_source(api: TestClient) -> None:
    binder = create_binder(api)
    first = fixture("sampling")
    deliver(api, binder["id"], first)
    again = copy.deepcopy(first)
    again["paper"]["ref"] = "D-3b"
    refused = deliver(api, binder["id"], again, 409)
    assert (
        "already received as paper D-3" in refused["detail"]
        and "one paper per run" in refused["detail"]
    )
    # The same id under another source is another module's run.
    other = fixture("analytical_review")
    other["generated"]["run_id"] = first["generated"]["run_id"]
    deliver(api, binder["id"], other)
    # Without a run id (optional for the three modules, decision 7) nothing collides.
    for ref in ("D-6", "D-7"):
        body = fixture("sampling")
        body["paper"]["ref"] = ref
        del body["generated"]["run_id"]
        assert deliver(api, binder["id"], body)["generated"]["run_id"] is None
    # A reused paper reference is refused as for any paper (spec 3B).
    body = fixture("sampling")
    body["generated"]["run_id"] = "fresh-run"
    assert "already used" in deliver(api, binder["id"], body, 409)["detail"]


def test_no_intake_after_assembly(api: TestClient) -> None:
    binder = complete_binder(api)
    act_as(api, PARTNER)
    assert api.post(f"/api/binders/{binder['id']}/assemble").status_code == 200
    refused = deliver(api, binder["id"], fixture("sampling"), 409)
    assert "assembled" in refused["detail"]  # decision 9
    act_as(api, PREPARER)


def test_module_fields_are_locked_and_the_conclusion_stays_human(api: TestClient) -> None:
    binder = create_binder(api)
    body = fixture("sampling")
    body["paper"]["conclusion"] = None
    paper = deliver(api, binder["id"], body)
    refused = api.patch(f"/api/papers/{paper['id']}", json={"result": "61 invoices examined."})
    assert refused.status_code == 422
    assert "result of D-3 came from oak_sampling (sampling)" in refused.json()["detail"]
    assert "not retyped here (spec 3C)" in refused.json()["detail"]
    for field, value in (
        ("title", "x"),
        ("section", "E"),
        ("sa_refs", ["SA 500"]),
        ("objective", "x"),
        ("procedure", "x"),
        ("population_sample", "x"),
    ):
        assert api.patch(f"/api/papers/{paper['id']}", json={field: value}).status_code == 422, (
            field
        )
    written = api.patch(
        f"/api/papers/{paper['id']}", json={"conclusion": "Revenue is supported by the sample."}
    )
    assert written.status_code == 200 and written.json()["conclusion"].startswith("Revenue")
    # The locked fields still hash to what arrived.
    from oak_binder.models.generation import LOCKED_FIELDS

    current = written.json()
    recomputed = content_hash({name: current[name] for name in LOCKED_FIELDS})
    assert recomputed == current["generated"]["content_hash_at_intake"]


def test_locked_fields_hold_through_amendments_after_assembly(api: TestClient) -> None:
    binder = complete_binder(api)
    paper = deliver(api, binder["id"], fixture("sampling"))
    full_chain(api, paper["id"])
    act_as(api, PARTNER)
    assert api.post(f"/api/binders/{binder['id']}/assemble").status_code == 200
    refused = api.patch(
        f"/api/papers/{paper['id']}",
        json={"result": "changed", "amendment_reason": "typo"},
    )
    assert refused.status_code == 422 and "not retyped here" in refused.json()["detail"]
    amended = api.patch(
        f"/api/papers/{paper['id']}",
        json={"conclusion": "Revised after partner review.", "amendment_reason": "partner review"},
    )
    assert amended.status_code == 200, amended.text
    assert amended.json()["versions"][-1]["amendment_reason"] == "partner review"
    assert "generated" in amended.json()["versions"][-1]["body"]
    act_as(api, PREPARER)


def test_the_provenance_block_is_size_capped(api: TestClient) -> None:
    binder = create_binder(api)
    settings_of(api).max_provenance_bytes = 400
    refused = deliver(api, binder["id"], fixture("sampling"), 413)
    assert "the limit is 400" in refused["detail"]


# --- who may deliver (decisions 8 and 12) ------------------------------------------------------


def test_an_intake_credential_is_required_when_configured(api: TestClient) -> None:
    binder = create_binder(api)
    settings_of(api).intake_credential = "example-credential"  # noqa: S105
    without = api.post(f"/api/binders/{binder['id']}/generated-papers", json=fixture("sampling"))
    assert without.status_code == 401 and without.headers["WWW-Authenticate"] == "Bearer"
    wrong = api.post(
        f"/api/binders/{binder['id']}/generated-papers",
        json=fixture("sampling"),
        headers={"Authorization": "Bearer other"},
    )
    assert wrong.status_code == 401
    ok = api.post(
        f"/api/binders/{binder['id']}/generated-papers",
        json=fixture("sampling"),
        headers={"Authorization": "Bearer example-credential"},
    )
    assert ok.status_code == 201, ok.text
    # Ordinary endpoints are not affected by the intake credential.
    assert api.get(f"/api/binders/{binder['id']}").status_code == 200


def test_under_header_auth_only_listed_identities_may_deliver(api: TestClient) -> None:
    binder = create_binder(api)
    settings = settings_of(api)
    settings.auth = "header"
    settings.dev_user = None
    headers = {"X-Authenticated-User": "sampling@oak"}
    nobody = api.post(
        f"/api/binders/{binder['id']}/generated-papers", json=fixture("sampling"), headers=headers
    )
    assert nobody.status_code == 403 and "no intake identities are configured" in nobody.text
    settings.intake_identities = "materiality@oak, sampling@oak"
    person = api.post(
        f"/api/binders/{binder['id']}/generated-papers",
        json=fixture("sampling"),
        headers={"X-Authenticated-User": "partner@firm"},
    )
    assert person.status_code == 403 and "not an authorised intake identity" in person.text
    module = api.post(
        f"/api/binders/{binder['id']}/generated-papers", json=fixture("sampling"), headers=headers
    )
    assert module.status_code == 201, module.text
    assert module.json()["generated"]["received_by"] == "sampling@oak"
    unauthenticated = api.post(
        f"/api/binders/{binder['id']}/generated-papers", json=fixture("sampling")
    )
    assert unauthenticated.status_code == 401


def test_intake_identity_list_parsing() -> None:
    from tests.conftest import APP_URL, IsolatedSettings

    listed = IsolatedSettings(env="test", database_url=APP_URL, intake_identities=" a@x, b@y ,,")
    assert listed.intake_identity_set() == {"a@x", "b@y"}
    none = IsolatedSettings(env="test", database_url=APP_URL)
    assert none.intake_identity_set() == frozenset()


# --- acceptance 8.8: the produced archive carries the formula and the seed ----------------------


def test_a_generated_sampling_paper_carries_its_formula_and_seed_into_the_archive(
    api: TestClient,
) -> None:
    binder = complete_binder(api)
    paper = deliver(api, binder["id"], fixture("sampling"))
    full_chain(api, paper["id"])
    act_as(api, PARTNER)
    assembled = api.post(f"/api/binders/{binder['id']}/assemble")
    assert assembled.status_code == 200, assembled.text
    manifest = assembled.json()["manifest"]
    listed = next(p for p in manifest["papers"] if p["ref"] == "D-3")
    produced = api.get(f"/api/binders/{binder['id']}/produce")
    assert produced.status_code == 200
    with zipfile.ZipFile(io.BytesIO(produced.content)) as archive:
        names = archive.namelist()
        folder = next(
            n
            for n in names
            if n.endswith("/paper.json") and json.loads(archive.read(n))["ref"] == "D-3"
        )
        folder = folder.rsplit("/", 1)[0]
        paper_json = json.loads(archive.read(f"{folder}/paper.json"))
        assert paper_json["generated_by"] == "sampling"
        bodies = [
            json.loads(archive.read(n))["body"]
            for n in sorted(names)
            if n.startswith(f"{folder}/versions/")
        ]
        assert len(bodies) == 3
        for body in bodies:
            sampling = body["generated"]["payload"]["sampling"]
            assert sampling == {
                "formula": "interval = population_value / sample_size",
                "seed": 20261031,
            }
            assert "interval = population_value / sample_size" in body["population_sample"]
            assert "20261031" in body["population_sample"]
        current = json.loads(archive.read(f"{folder}/versions/0003.json"))
        assert current["content_hash"] == listed["content_hash"] == content_hash(current["body"])
        # A hand-made paper's record has no generated_by key at all.
        other = next(
            json.loads(archive.read(n))
            for n in names
            if n.endswith("/paper.json") and json.loads(archive.read(n))["ref"] == "C-1"
        )
        assert "generated_by" not in other
    act_as(api, REVIEWER)
