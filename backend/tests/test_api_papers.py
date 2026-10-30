"""Working papers over the API against oak_binder_test: creation, editing, the version
history and the sign-off workflow (spec 3B, 3D, 8.1, 8.2, 8.9)."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from oak_binder.hashing import content_hash
from tests.conftest import PREPARER, REVIEWER, act_as, unique

pytestmark = pytest.mark.db

PARTNER = "partner@firm"

PAPER = {
    "ref": "D-1",
    "section": "D",
    "title": "Cash and bank",
    "sa_refs": ["SA 500", "SA 505"],
    "objective": "Existence and accuracy of cash at year end",
    "procedure": "Bank confirmations and reconciliations",
    "population_sample": "All 4 bank accounts",
    "result": "No exceptions",
    "conclusion": "Cash is fairly stated",
}


def new_paper(api: TestClient, **overrides: Any) -> dict[str, Any]:
    binder = api.post("/api/binders", json={"engagement": unique("ENG"), "template": "statutory"})
    assert binder.status_code == 201, binder.text
    response = api.post(f"/api/binders/{binder.json()['id']}/papers", json={**PAPER, **overrides})
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


def step(api: TestClient, paper_id: str, action: str, expected: int = 200) -> dict[str, Any]:
    response = api.post(f"/api/papers/{paper_id}/{action}")
    assert response.status_code == expected, f"{action}: {response.status_code} {response.text}"
    result: dict[str, Any] = response.json()
    return result


def full_chain(api: TestClient, paper_id: str) -> dict[str, Any]:
    """prepare as PREPARER, submit, review as REVIEWER, sign off as PARTNER."""
    act_as(api, PREPARER)
    step(api, paper_id, "prepare")
    step(api, paper_id, "submit")
    act_as(api, REVIEWER)
    step(api, paper_id, "review")
    act_as(api, PARTNER)
    return step(api, paper_id, "sign-off")


# --- creation and editing (spec 3B) -----------------------------------------------------------


def test_create_paper_with_every_spec_field(api: TestClient) -> None:
    paper = new_paper(api)
    assert paper["status"] == "draft"
    assert paper["current_version"] is None
    assert paper["versions"] == []
    for field, value in PAPER.items():
        assert paper[field] == value


def test_reference_is_unique_and_immutable(api: TestClient) -> None:
    paper = new_paper(api)
    duplicate = api.post(f"/api/binders/{paper['binder_id']}/papers", json=PAPER)
    assert duplicate.status_code == 409
    assert "never reused" in duplicate.json()["detail"]
    renamed = api.patch(f"/api/papers/{paper['id']}", json={"ref": "D-2"})
    assert renamed.status_code == 422


def test_content_validation(api: TestClient) -> None:
    binder = api.post("/api/binders", json={"engagement": unique("ENG"), "template": "statutory"})
    url = f"/api/binders/{binder.json()['id']}/papers"
    assert api.post(url, json={**PAPER, "section": "U"}).status_code == 422
    assert api.post(url, json={**PAPER, "title": "  "}).status_code == 422
    assert api.post(url, json={**PAPER, "ref": ""}).status_code == 422
    lower = api.post(url, json={**PAPER, "section": "d", "sa_refs": [" SA 500 ", ""]})
    assert lower.status_code == 201
    assert lower.json()["section"] == "D"
    assert lower.json()["sa_refs"] == ["SA 500"]


def test_an_amendment_reason_is_refused_on_an_open_binder(api: TestClient) -> None:
    paper = new_paper(api)
    refused = api.patch(
        f"/api/papers/{paper['id']}", json={"conclusion": "x", "amendment_reason": "why"}
    )
    assert refused.status_code == 422
    assert "applies to an assembled binder only" in refused.json()["detail"]
    assert api.get(f"/api/papers/{paper['id']}").json()["conclusion"] == PAPER["conclusion"]


def test_edit_changes_fields_and_unknown_paper_is_404(api: TestClient) -> None:
    paper = new_paper(api)
    edited = api.patch(f"/api/papers/{paper['id']}", json={"title": "Cash", "result": None})
    assert edited.status_code == 200
    assert edited.json()["title"] == "Cash"
    assert edited.json()["result"] is None
    assert edited.json()["conclusion"] == PAPER["conclusion"]  # untouched
    assert api.get("/api/papers/00000000-0000-0000-0000-000000000000").status_code == 404


# --- the workflow (spec 3B status chain, 3D, 8.9) ---------------------------------------------


def test_full_sign_off_records_who_when_and_which_version(api: TestClient) -> None:
    paper = new_paper(api)

    act_as(api, PREPARER)
    prepared = step(api, paper["id"], "prepare")
    assert prepared["status"] == "prepared"
    assert prepared["current_version"] == 1
    (v1,) = prepared["versions"]
    assert v1["prepared_by"] == PREPARER and v1["prepared_at"]
    assert v1["reviewed_by"] is None and v1["reviewed_at"] is None
    assert v1["signed_off_by"] is None and v1["signed_off_at"] is None
    assert v1["body"]["conclusion"] == PAPER["conclusion"]
    assert v1["content_hash"] == content_hash(v1["body"])

    submitted = step(api, paper["id"], "submit")
    assert submitted["status"] == "in_review"
    assert len(submitted["versions"]) == 1

    act_as(api, REVIEWER)
    reviewed = step(api, paper["id"], "review")
    assert reviewed["status"] == "reviewed"
    assert reviewed["current_version"] == 2
    v2 = reviewed["versions"][1]
    assert v2["prepared_by"] == PREPARER and v2["prepared_at"] == v1["prepared_at"]
    assert v2["reviewed_by"] == REVIEWER and v2["reviewed_at"]
    assert v2["signed_off_by"] is None
    assert v2["content_hash"] == v1["content_hash"]

    act_as(api, PARTNER)
    signed = step(api, paper["id"], "sign-off")
    assert signed["status"] == "signed_off"
    assert signed["current_version"] == 3
    v3 = signed["versions"][2]
    assert v3["prepared_by"] == PREPARER and v3["prepared_at"] == v1["prepared_at"]
    assert v3["reviewed_by"] == REVIEWER and v3["reviewed_at"] == v2["reviewed_at"]
    assert v3["signed_off_by"] == PARTNER and v3["signed_off_at"]
    assert v3["content_hash"] == v1["content_hash"]

    listed = api.get(f"/api/papers/{paper['id']}/versions").json()
    assert [v["version"] for v in listed] == [1, 2, 3]


def test_steps_only_run_in_order(api: TestClient) -> None:
    paper = new_paper(api)
    for action in ("submit", "review", "sign-off"):
        step(api, paper["id"], action, 409)
    step(api, paper["id"], "prepare")
    assert "not draft" in step(api, paper["id"], "prepare", 409)["detail"]
    assert "not in_review" in step(api, paper["id"], "review", 409)["detail"]
    assert "not reviewed" in step(api, paper["id"], "sign-off", 409)["detail"]


def test_sign_off_requires_a_conclusion(api: TestClient) -> None:
    # Spec 8.1. Preparing and reviewing an inconclusive paper is allowed; signing it off is not.
    paper = new_paper(api, conclusion=None)
    step(api, paper["id"], "prepare")
    step(api, paper["id"], "submit")
    act_as(api, REVIEWER)
    step(api, paper["id"], "review")
    refused = step(api, paper["id"], "sign-off", 422)
    assert "no conclusion" in refused["detail"]
    # A blank conclusion is no conclusion: nothing changes, so the status stays.
    blank = api.patch(f"/api/papers/{paper['id']}", json={"conclusion": "   "}).json()
    assert blank["conclusion"] is None and blank["status"] == "reviewed"
    # A real conclusion is a content change: back to draft, through the chain, then signed.
    concluded = api.patch(f"/api/papers/{paper['id']}", json={"conclusion": "Fairly stated"})
    assert concluded.json()["status"] == "draft"
    signed = full_chain(api, paper["id"])
    assert signed["status"] == "signed_off" and signed["current_version"] == 5


def test_sign_off_is_blocked_by_an_open_review_note(api: TestClient) -> None:
    # Spec 8.2, with real notes (test_api_review_notes covers every transition).
    paper = new_paper(api)
    step(api, paper["id"], "prepare")
    step(api, paper["id"], "submit")
    step(api, paper["id"], "review")
    for text in ("Point one", "Point two"):
        api.post(f"/api/papers/{paper['id']}/review-notes", json={"text": text}).raise_for_status()
    refused = step(api, paper["id"], "sign-off", 409)
    assert "2 open review note" in refused["detail"]


def test_an_edit_returns_the_paper_to_draft_and_keeps_its_versions(api: TestClient) -> None:
    paper = new_paper(api)
    step(api, paper["id"], "prepare")
    step(api, paper["id"], "submit")
    edited = api.patch(f"/api/papers/{paper['id']}", json={"result": "One exception"}).json()
    assert edited["status"] == "draft"
    assert edited["current_version"] == 1  # still the last signed-off version
    assert len(edited["versions"]) == 1
    assert edited["versions"][0]["body"]["result"] == "No exceptions"  # the snapshot is frozen
    prepared_again = step(api, paper["id"], "prepare")
    assert prepared_again["current_version"] == 2
    assert prepared_again["versions"][1]["body"]["result"] == "One exception"


def test_editing_a_signed_off_paper_returns_it_to_draft_and_keeps_every_version(
    api: TestClient,
) -> None:
    # Spec 3B, 3D, 8.9 and architecture D14: the sign-offs on file refer to the versions
    # they signed, which must survive any later edit byte for byte.
    paper = new_paper(api)
    signed = full_chain(api, paper["id"])
    assert signed["status"] == "signed_off" and signed["current_version"] == 3
    before = signed["versions"]
    assert [v["version"] for v in before] == [1, 2, 3]
    assert before[2]["signed_off_by"] == PARTNER

    edited = api.patch(f"/api/papers/{paper['id']}", json={"conclusion": "Revised conclusion"})
    assert edited.status_code == 200
    body = edited.json()
    # 1. back to draft, with the live field changed
    assert body["status"] == "draft"
    assert body["conclusion"] == "Revised conclusion"
    # 2. and 3. every earlier version is still there, identical in every field
    assert body["versions"] == before
    assert body["current_version"] == 3  # still points at the last signed version
    for v in body["versions"]:
        assert v["body"]["conclusion"] == PAPER["conclusion"]
    assert body["versions"][2]["signed_off_at"] == before[2]["signed_off_at"]

    # Signing the revised content off again appends; it never rewrites.
    again = full_chain(api, paper["id"])
    assert again["current_version"] == 6
    assert again["versions"][:3] == before
    assert [v["version"] for v in again["versions"]] == [1, 2, 3, 4, 5, 6]
    assert again["versions"][3]["body"]["conclusion"] == "Revised conclusion"
    assert again["versions"][3]["content_hash"] != before[0]["content_hash"]
    listed = api.get(f"/api/papers/{paper['id']}/versions").json()
    assert listed == again["versions"]


def test_an_edit_that_changes_nothing_keeps_the_status(api: TestClient) -> None:
    paper = new_paper(api)
    step(api, paper["id"], "prepare")
    same = api.patch(f"/api/papers/{paper['id']}", json={"title": PAPER["title"]}).json()
    assert same["status"] == "prepared"


def test_every_sign_off_step_needs_an_identity(api: TestClient) -> None:
    paper = new_paper(api)
    act_as(api, None)
    assert api.post(f"/api/papers/{paper['id']}/prepare").status_code == 503
    act_as(api, PREPARER)
    step(api, paper["id"], "prepare")
    step(api, paper["id"], "submit")
    act_as(api, None)
    assert api.post(f"/api/papers/{paper['id']}/review").status_code == 503
    act_as(api, REVIEWER)
    step(api, paper["id"], "review")
    act_as(api, None)
    assert api.post(f"/api/papers/{paper['id']}/sign-off").status_code == 503
