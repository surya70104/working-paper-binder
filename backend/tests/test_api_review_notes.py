"""Review notes over the API against oak_binder_test (spec 3D, 5.3, 8.2, 8.3): every
transition in order, out-of-order refused, and an open note blocking sign-off and assembly."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.conftest import PREPARER, REVIEWER, act_as
from tests.helpers import PARTNER, complete_binder, create_binder, create_paper, full_chain, step

pytestmark = pytest.mark.db


def raise_note(
    api: TestClient, paper_id: str, text: str = "Tie the balance to the bank statement"
) -> dict[str, Any]:
    response = api.post(f"/api/papers/{paper_id}/review-notes", json={"text": text})
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


def move(
    api: TestClient,
    note_id: str,
    action: str,
    body: dict[str, Any] | None = None,
    expected: int = 200,
) -> dict[str, Any]:
    response = api.post(f"/api/review-notes/{note_id}/{action}", json=body)
    assert response.status_code == expected, f"{action}: {response.status_code} {response.text}"
    result: dict[str, Any] = response.json()
    return result


def paper_in_review(api: TestClient) -> dict[str, Any]:
    paper = create_paper(api, create_binder(api)["id"])
    act_as(api, PREPARER)
    step(api, paper["id"], "prepare")
    step(api, paper["id"], "submit")
    return paper


# --- the chain raised -> assigned -> responded -> cleared (spec 3D) ---------------------------


def test_every_transition_in_order_records_who_and_when(api: TestClient) -> None:
    paper = paper_in_review(api)
    act_as(api, REVIEWER)
    note = raise_note(api, paper["id"])
    assert note["state"] == "raised" and note["open"] is True
    assert note["raised_by"] == REVIEWER and note["raised_at"]
    assert note["text"] == "Tie the balance to the bank statement"
    assert [s["state"] for s in note["steps"]] == ["raised"]

    assigned = move(api, note["note_id"], "assign", {"assigned_to": PREPARER})
    assert assigned["state"] == "assigned" and assigned["assigned_to"] == PREPARER
    assert assigned["steps"][1]["actor"] == REVIEWER

    act_as(api, PREPARER)
    responded = move(api, note["note_id"], "respond", {"text": "Reconciled; difference is timing"})
    assert responded["state"] == "responded"
    assert responded["response"] == "Reconciled; difference is timing"
    assert responded["responded_at"] and responded["steps"][2]["actor"] == PREPARER
    assert responded["open"] is True  # responded is not cleared

    act_as(api, REVIEWER)
    cleared = move(api, note["note_id"], "clear")
    assert cleared["state"] == "cleared" and cleared["open"] is False
    assert cleared["cleared_by"] == REVIEWER and cleared["cleared_at"]
    assert [s["state"] for s in cleared["steps"]] == ["raised", "assigned", "responded", "cleared"]
    assert cleared["text"] == note["text"]  # the raised text survives every step

    listed = api.get(f"/api/papers/{paper['id']}/review-notes").json()
    assert [n["state"] for n in listed] == ["cleared"]
    assert api.get(f"/api/review-notes/{note['note_id']}").json()["state"] == "cleared"


def test_steps_out_of_order_are_refused(api: TestClient) -> None:
    paper = paper_in_review(api)
    note = raise_note(api, paper["id"])
    nid = note["note_id"]
    assert "cannot be responded now" in move(api, nid, "respond", {"text": "x"}, 409)["detail"]
    assert "cannot be cleared now" in move(api, nid, "clear", None, 409)["detail"]
    move(api, nid, "assign", {"assigned_to": PREPARER})
    assert (
        "cannot be assigned now"
        in move(api, nid, "assign", {"assigned_to": PARTNER}, 409)["detail"]
    )
    assert "cannot be cleared now" in move(api, nid, "clear", None, 409)["detail"]
    move(api, nid, "respond", {"text": "done"})
    assert "cannot be responded now" in move(api, nid, "respond", {"text": "again"}, 409)["detail"]
    move(api, nid, "clear")
    assert (
        "cannot be assigned now"
        in move(api, nid, "assign", {"assigned_to": PREPARER}, 409)["detail"]
    )
    assert "cannot be cleared now" in move(api, nid, "clear", None, 409)["detail"]


def test_validation(api: TestClient) -> None:
    paper = paper_in_review(api)
    assert (
        api.post(f"/api/papers/{paper['id']}/review-notes", json={"text": "  "}).status_code == 422
    )
    assert (
        api.post(f"/api/papers/{paper['id']}/review-notes", json={"note": "x"}).status_code == 422
    )
    note = raise_note(api, paper["id"])
    assert move(api, note["note_id"], "assign", {"assigned_to": " "}, 422)
    move(api, note["note_id"], "assign", {"assigned_to": PREPARER})
    assert move(api, note["note_id"], "respond", {"text": ""}, 422)
    assert api.get("/api/review-notes/00000000-0000-0000-0000-000000000000").status_code == 404
    act_as(api, None)
    assert (
        api.post(f"/api/papers/{paper['id']}/review-notes", json={"text": "x"}).status_code == 503
    )


# --- spec 8.2: an open note blocks sign-off ------------------------------------------------------


def test_open_note_blocks_sign_off_until_cleared(api: TestClient) -> None:
    paper = paper_in_review(api)
    act_as(api, REVIEWER)
    note = raise_note(api, paper["id"])
    step(api, paper["id"], "review")  # reviewing is allowed; signing off is not
    refused = step(api, paper["id"], "sign-off", 409)
    assert "1 open review note" in refused["detail"]
    assert api.get(f"/api/papers/{paper['id']}").json()["open_review_notes"] == 1

    move(api, note["note_id"], "assign", {"assigned_to": PREPARER})
    assert "1 open review note" in step(api, paper["id"], "sign-off", 409)["detail"]
    act_as(api, PREPARER)
    move(api, note["note_id"], "respond", {"text": "Addressed in the reconciliation"})
    act_as(api, REVIEWER)
    assert (
        "1 open review note" in step(api, paper["id"], "sign-off", 409)["detail"]
    )  # responded still blocks

    move(api, note["note_id"], "clear")
    second = raise_note(api, paper["id"], "Second point")
    assert "1 open review note" in step(api, paper["id"], "sign-off", 409)["detail"]
    move(api, second["note_id"], "assign", {"assigned_to": PREPARER})
    move(api, second["note_id"], "respond", {"text": "ok"})
    move(api, second["note_id"], "clear")
    act_as(api, PARTNER)
    signed = step(api, paper["id"], "sign-off")
    assert signed["status"] == "signed_off" and signed["open_review_notes"] == 0


# --- spec 8.3: an open note blocks assembly, named -----------------------------------------------


def test_open_note_blocks_assembly_by_name(api: TestClient) -> None:
    binder = complete_binder(api)
    status = api.get(f"/api/binders/{binder['id']}/assembly").json()
    assert status["blockers"] == []
    assert len(status["not_checked"]) == 1 and "FS lines" in status["not_checked"][0]
    assert not any("review note" in n for n in status["not_checked"])

    c1 = next(p for s in binder["sections"] for p in s["papers"] if p["ref"] == "C-1")
    act_as(api, REVIEWER)
    note = raise_note(api, c1["id"], "Benchmark not justified")
    status = api.get(f"/api/binders/{binder['id']}/assembly").json()
    assert [(b["kind"], b["ref"], b["detail"]) for b in status["blockers"]] == [
        ("open_review_notes", "C-1", "1 open review note(s)")
    ]
    refused = api.post(f"/api/binders/{binder['id']}/assemble")
    assert refused.status_code == 409 and "open_review_notes C-1" in refused.json()["detail"]

    for action, body in (
        ("assign", {"assigned_to": PREPARER}),
        ("respond", {"text": "Added"}),
        ("clear", None),
    ):
        move(api, note["note_id"], action, body)
    assert api.get(f"/api/binders/{binder['id']}/assembly").json()["blockers"] == []
    assert api.post(f"/api/binders/{binder['id']}/assemble").status_code == 200


def test_binder_note_list_says_what_is_open_and_what_it_blocks(api: TestClient) -> None:
    binder = create_binder(api)
    a = create_paper(api, binder["id"], ref="D-1")
    b = create_paper(api, binder["id"], ref="D-2", title="Receivables")
    act_as(api, REVIEWER)
    raise_note(api, a["id"], "Cut-off")
    second = raise_note(api, b["id"], "Ageing")
    for action, body in (
        ("assign", {"assigned_to": PREPARER}),
        ("respond", {"text": "ok"}),
        ("clear", None),
    ):
        move(api, second["note_id"], action, body)
    listed = api.get(f"/api/binders/{binder['id']}/review-notes").json()
    assert [(n["ref"], n["title"], n["state"], n["open"], n["raised_by"]) for n in listed] == [
        ("D-1", "Cash and bank", "raised", True, REVIEWER),
        ("D-2", "Receivables", "cleared", False, REVIEWER),
    ]
    assert listed[0]["paper_status"] == "draft"


def test_no_note_step_can_be_taken_on_a_purged_binder(api: TestClient) -> None:
    from datetime import date
    from typing import cast

    from fastapi import FastAPI

    from oak_binder.api import deps

    binder = complete_binder(api, report_date="2026-09-30")
    detail = api.get(f"/api/binders/{binder['id']}").json()
    c1 = next(p for s in detail["sections"] for p in s["papers"] if p["ref"] == "C-1")
    act_as(api, REVIEWER)
    note = raise_note(api, c1["id"], "Late point")  # raised before assembly...
    move(api, note["note_id"], "assign", {"assigned_to": PREPARER})
    move(api, note["note_id"], "respond", {"text": "done"})
    move(api, note["note_id"], "clear")
    api.post(f"/api/binders/{binder['id']}/assemble").raise_for_status()
    second = raise_note(api, c1["id"], "Post-assembly point")  # ...and one left open
    move(api, second["note_id"], "assign", {"assigned_to": PREPARER})
    cast(FastAPI, api.app).dependency_overrides[deps.today] = lambda: date(2033, 9, 30)
    act_as(api, PARTNER)
    api.post(f"/api/binders/{binder['id']}/purge").raise_for_status()
    refused = move(api, second["note_id"], "respond", {"text": "too late"}, 409)
    assert "purged" in refused["detail"]
    assert "purged" in move(api, second["note_id"], "clear", None, 409)["detail"]
    assert api.get(f"/api/review-notes/{second['note_id']}").json()["state"] == "assigned"


def test_notes_survive_sign_off_and_reopen_on_a_new_note(api: TestClient) -> None:
    paper = create_paper(api, create_binder(api)["id"])
    full_chain(api, paper["id"])
    act_as(api, REVIEWER)
    raise_note(api, paper["id"], "Late point")  # a note on a signed-off paper is allowed
    assert api.get(f"/api/papers/{paper['id']}").json()["open_review_notes"] == 1
    # It blocks assembly of its binder even though the paper is signed off.
    status = api.get(f"/api/binders/{paper['binder_id']}/assembly").json()
    assert ("open_review_notes", "D-1") in {(b["kind"], b["ref"]) for b in status["blockers"]}
