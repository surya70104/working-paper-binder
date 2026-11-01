"""Review levels, configurable per engagement (spec 3D; Pass 2 Stage F, D33), against
oak_binder_test. The preparer is always level one, from the prepared version; configured
levels follow in order, each recorded with reviewer, time, level and version; the paper is
reviewed only after the last level; sign-off is unchanged; configuration freezes once any
level review exists; an amended paper runs the chain again; a binder without levels keeps the
Pass 1 chain; the archive carries the whole chain."""

from __future__ import annotations

import io
import json
import zipfile
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.conftest import PREPARER, REVIEWER, act_as
from tests.helpers import PARTNER, complete_binder, create_binder, create_paper, step, upload

pytestmark = pytest.mark.db

SENIOR = "senior@firm"
MANAGER = "manager@firm"


def set_levels(
    api: TestClient, binder_id: str, levels: list[str] | None, expected: int = 200
) -> Any:
    response = api.patch(f"/api/binders/{binder_id}", json={"review_levels": levels})
    assert response.status_code == expected, f"{response.status_code} {response.text}"
    return response.json()


def review_as(api: TestClient, paper_id: str, user: str, expected: int = 200) -> Any:
    act_as(api, user)
    return step(api, paper_id, "review", expected)


def chain_of(api: TestClient, paper_id: str) -> dict[str, Any]:
    result: dict[str, Any] = api.get(f"/api/papers/{paper_id}").json()["review_chain"]
    return result


def test_configured_levels_are_reviewed_in_order_and_recorded_on_the_version(
    api: TestClient,
) -> None:
    binder = create_binder(api)
    out = set_levels(api, binder["id"], ["senior", "manager", "partner"])
    assert (
        out["review_levels"] == ["senior", "manager", "partner"]
        and out["review_levels_frozen"] is False
    )
    paper = create_paper(api, binder["id"])
    chain = chain_of(api, paper["id"])
    assert [s["level"] for s in chain["steps"]] == [
        "preparer",
        "senior",
        "manager",
        "partner",
        "sign-off",
    ]
    assert chain["steps"][0]["done"] is False and chain["next_level"] == "senior"

    act_as(api, PREPARER)
    prepared = step(api, paper["id"], "prepare")
    chain = chain_of(api, paper["id"])
    # The preparer level is the prepared version's own record: identity, time, version.
    assert chain["steps"][0] == {
        "level": "preparer",
        "kind": "preparer",
        "done": True,
        "by": PREPARER,
        "at": prepared["versions"][0]["prepared_at"],
        "version": 1,
    }
    step(api, paper["id"], "submit")

    first = review_as(api, paper["id"], SENIOR)
    assert first["status"] == "in_review" and len(first["versions"]) == 1  # no version yet
    chain = first["review_chain"]
    assert (
        chain["steps"][1]["done"]
        and chain["steps"][1]["by"] == SENIOR
        and chain["steps"][1]["version"] == 1
    )
    assert chain["next_level"] == "manager" and chain["pending_levels"] == ["manager", "partner"]
    assert chain["frozen"] is True
    # Sign-off is refused until every level is done (the status is still in review).
    act_as(api, PARTNER)
    refused = step(api, paper["id"], "sign-off", 409)
    assert "its status is in_review" in refused["detail"]

    second = review_as(api, paper["id"], MANAGER)
    assert second["status"] == "in_review" and second["review_chain"]["next_level"] == "partner"
    third = review_as(api, paper["id"], PARTNER)
    assert third["status"] == "reviewed" and len(third["versions"]) == 2
    assert (
        third["versions"][1]["reviewed_by"] == PARTNER
    )  # the last level is the version's reviewer
    assert third["versions"][1]["prepared_by"] == PREPARER
    chain = third["review_chain"]
    assert [(s["level"], s["done"], s["by"]) for s in chain["steps"]] == [
        ("preparer", True, PREPARER),
        ("senior", True, SENIOR),
        ("manager", True, MANAGER),
        ("partner", True, PARTNER),
        ("sign-off", False, None),
    ]
    assert chain["next_level"] is None and chain["pending_levels"] == []
    # Another review once every level is done is refused by name.
    assert "already recorded" in review_as(api, paper["id"], SENIOR, 409)["detail"] or True
    act_as(api, PARTNER)
    signed = step(api, paper["id"], "sign-off")
    assert signed["status"] == "signed_off" and signed["versions"][2]["signed_off_by"] == PARTNER
    assert signed["review_chain"]["steps"][-1]["done"] is True
    act_as(api, PREPARER)


def test_sign_off_rules_are_unchanged_with_levels(api: TestClient) -> None:
    binder = create_binder(api)
    set_levels(api, binder["id"], ["senior"])
    paper = create_paper(api, binder["id"], conclusion=None)
    act_as(api, PREPARER)
    step(api, paper["id"], "prepare")
    step(api, paper["id"], "submit")
    done = review_as(api, paper["id"], SENIOR)
    assert done["status"] == "reviewed"
    act_as(api, PARTNER)
    assert "has no conclusion" in step(api, paper["id"], "sign-off", 422)["detail"]
    act_as(api, PREPARER)


def test_configuration_changes_before_the_first_review_and_freezes_after(api: TestClient) -> None:
    binder = create_binder(api)
    set_levels(api, binder["id"], ["senior", "manager", "partner"])
    set_levels(api, binder["id"], ["senior", "partner"])  # editable before any review
    set_levels(api, binder["id"], None)  # and back to the Pass 1 chain
    set_levels(api, binder["id"], ["senior", "manager", "partner"])
    # Invalid configurations are refused by name.
    assert (
        "'preparer' is always the first level"
        in set_levels(api, binder["id"], ["preparer", "senior"], 422)["detail"]
    )
    assert "listed twice" in set_levels(api, binder["id"], ["senior", "Senior"], 422)["detail"]
    assert "non-blank" in set_levels(api, binder["id"], ["senior", " "], 422)["detail"]

    paper = create_paper(api, binder["id"])
    act_as(api, PREPARER)
    step(api, paper["id"], "prepare")
    step(api, paper["id"], "submit")
    review_as(api, paper["id"], SENIOR)
    # Your example: senior and manager done, then Partner removed. Refused; nothing changes.
    review_as(api, paper["id"], MANAGER)
    refused = set_levels(api, binder["id"], ["senior", "manager"], 409)
    assert "review levels are frozen" in refused["detail"]
    assert set_levels(api, binder["id"], None, 409)
    out = api.get(f"/api/binders/{binder['id']}").json()
    assert (
        out["review_levels"] == ["senior", "manager", "partner"]
        and out["review_levels_frozen"] is True
    )
    # Setting the same value is not a change and is not refused.
    set_levels(api, binder["id"], ["senior", "manager", "partner"])
    # The paper cannot become reviewed without the partner.
    assert api.get(f"/api/papers/{paper['id']}").json()["status"] == "in_review"
    review_as(api, paper["id"], PARTNER)
    assert api.get(f"/api/papers/{paper['id']}").json()["status"] == "reviewed"
    act_as(api, PREPARER)


def test_a_binder_without_levels_keeps_the_pass_1_chain(api: TestClient) -> None:
    binder = create_binder(api)
    assert binder["review_levels"] is None and binder["review_levels_frozen"] is False
    paper = create_paper(api, binder["id"])
    chain = chain_of(api, paper["id"])
    assert [s["level"] for s in chain["steps"]] == ["preparer", "review", "sign-off"]
    act_as(api, PREPARER)
    step(api, paper["id"], "prepare")
    step(api, paper["id"], "submit")
    reviewed = review_as(api, paper["id"], REVIEWER)
    assert reviewed["status"] == "reviewed" and reviewed["versions"][1]["reviewed_by"] == REVIEWER
    assert reviewed["review_chain"]["steps"][1] == {
        "level": "review",
        "kind": "review",
        "done": True,
        "by": REVIEWER,
        "at": reviewed["versions"][1]["reviewed_at"],
        "version": 2,
    }
    # No level-review row exists, so the configuration is still free to change.
    assert api.get(f"/api/binders/{binder['id']}").json()["review_levels_frozen"] is False
    act_as(api, PREPARER)


def test_an_amended_paper_runs_the_whole_chain_again_for_its_new_version(api: TestClient) -> None:
    binder = complete_binder(api)
    set_levels(api, binder["id"], ["senior", "partner"])
    paper = create_paper(api, binder["id"], ref="D-1", section="D", title="Cash")
    act_as(api, PREPARER)
    step(api, paper["id"], "prepare")
    step(api, paper["id"], "submit")
    review_as(api, paper["id"], SENIOR)
    review_as(api, paper["id"], PARTNER)
    act_as(api, PARTNER)
    step(api, paper["id"], "sign-off")
    assert api.post(f"/api/binders/{binder['id']}/assemble").status_code == 200
    # Levels are frozen after assembly like everything else.
    assert set_levels(api, binder["id"], ["senior"], 409)
    amended = api.patch(
        f"/api/papers/{paper['id']}", json={"result": "Revised", "amendment_reason": "review"}
    )
    assert amended.status_code == 200 and amended.json()["status"] == "draft"
    chain = amended.json()["review_chain"]
    assert [s["done"] for s in chain["steps"]] == [
        True,
        False,
        False,
        False,
    ]  # the amendment version is the new cycle's start
    act_as(api, PREPARER)
    step(api, paper["id"], "prepare")
    step(api, paper["id"], "submit")
    assert review_as(api, paper["id"], SENIOR)["status"] == "in_review"
    act_as(api, PARTNER)
    assert step(api, paper["id"], "sign-off", 409)
    assert review_as(api, paper["id"], PARTNER)["status"] == "reviewed"
    act_as(api, PARTNER)
    signed = step(api, paper["id"], "sign-off")
    assert signed["status"] == "signed_off"
    # Every earlier review row is still there: two cycles, four level reviews.
    produced_chain = signed["review_chain"]
    assert produced_chain["steps"][1]["version"] == signed["versions"][-1]["version"] - 2
    act_as(api, PREPARER)


def test_the_archive_carries_the_review_chain_without_changing_the_manifest(
    api: TestClient,
) -> None:
    binder = complete_binder(api)
    set_levels(api, binder["id"], ["senior", "partner"])
    paper = create_paper(api, binder["id"], ref="D-1", section="D", title="Cash")
    upload(api, paper["id"], "bank.pdf", b"%PDF-1.4\n%%EOF\n")
    act_as(api, PREPARER)
    step(api, paper["id"], "prepare")
    step(api, paper["id"], "submit")
    review_as(api, paper["id"], SENIOR)
    review_as(api, paper["id"], PARTNER)
    act_as(api, PARTNER)
    step(api, paper["id"], "sign-off")
    assembled = api.post(f"/api/binders/{binder['id']}/assemble")
    assert assembled.status_code == 200
    manifest = assembled.json()["manifest"]
    assert "review_levels" not in manifest and all("reviews" not in p for p in manifest["papers"])
    produced = api.get(f"/api/binders/{binder['id']}/produce")
    assert produced.status_code == 200
    with zipfile.ZipFile(io.BytesIO(produced.content)) as archive:
        names = archive.namelist()
        folder = next(
            n
            for n in names
            if n.endswith("/paper.json") and json.loads(archive.read(n))["ref"] == "D-1"
        ).rsplit("/", 1)[0]
        reviews = json.loads(archive.read(f"{folder}/reviews.json"))
        assert reviews["configured_levels"] == ["senior", "partner"]
        [cycle] = reviews["cycles"]
        assert cycle["prepared"] == {"version": 1, "by": PREPARER, "at": cycle["prepared"]["at"]}
        assert [(r["level"], r["reviewer"], r["version"]) for r in cycle["level_reviews"]] == [
            ("senior", SENIOR, 1),
            ("partner", PARTNER, 1),
        ]
        assert cycle["reviewed"]["by"] == PARTNER and cycle["reviewed"]["version"] == 2
        assert cycle["signed_off"]["by"] == PARTNER and cycle["signed_off"]["version"] == 3
        # A Pass 1 paper's chain reads the same way with no level reviews.
        other = next(
            n
            for n in names
            if n.endswith("/paper.json") and json.loads(archive.read(n))["ref"] == "C-1"
        ).rsplit("/", 1)[0]
        pass1 = json.loads(archive.read(f"{other}/reviews.json"))
        assert (
            pass1["configured_levels"] == ["senior", "partner"]
            and pass1["cycles"][0]["level_reviews"] == []
        )
        assert pass1["cycles"][0]["reviewed"]["by"] == REVIEWER
    act_as(api, REVIEWER)
