"""Cross-references over the API (spec 3B, 3E, 3F, 8.3; D26): in and out on the paper, one
target each, within the binder, frozen at assembly; a broken reference is named and blocks
assembly; an FS-line reference is reported as not checked."""

from __future__ import annotations

import io
import json
import uuid
import zipfile
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.conftest import PREPARER, REVIEWER, act_as
from tests.helpers import (
    PARTNER,
    PDF,
    complete_binder,
    create_binder,
    create_paper,
    full_chain,
    step,
    upload,
)

pytestmark = pytest.mark.db


def add(api: TestClient, paper_id: str, expected: int = 201, **body: Any) -> dict[str, Any]:
    response = api.post(f"/api/papers/{paper_id}/xrefs", json=body)
    assert response.status_code == expected, f"{response.status_code} {response.text}"
    result: dict[str, Any] = response.json()
    return result


def xrefs_of(api: TestClient, paper_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = api.get(f"/api/papers/{paper_id}/xrefs").json()
    return rows


def blockers(api: TestClient, binder_id: str) -> set[tuple[str, str | None]]:
    status = api.get(f"/api/binders/{binder_id}/assembly").json()
    return {(b["kind"], b["ref"]) for b in status["blockers"]}


def test_a_reference_appears_on_both_papers_in_and_out(api: TestClient) -> None:
    binder = create_binder(api)
    cash = create_paper(api, binder["id"], ref="D-1", section="D", title="Cash")
    bank = create_paper(api, binder["id"], ref="D-2", section="D", title="Bank reconciliation")

    paper = add(api, cash["id"], to_wp=bank["id"], direction="to")
    [out] = paper["xrefs"]
    assert out["from_ref"] == "D-1" and out["to_ref"] == "D-2"
    assert out["outgoing"] is True and out["broken"] is None and out["checked"] is True
    assert out["created_by"] == PREPARER and out["created_at"]

    [incoming] = xrefs_of(api, bank["id"])
    assert incoming["id"] == out["id"]
    assert incoming["outgoing"] is False  # read from D-2, D-1 refers to it

    # 'from' reverses the reading: D-2 records that D-1 refers to it.
    paper = add(api, bank["id"], to_wp=cash["id"], direction="from")
    reverse = next(x for x in paper["xrefs"] if x["direction"] == "from")
    assert reverse["outgoing"] is False
    assert next(x for x in xrefs_of(api, cash["id"]) if x["id"] == reverse["id"])["outgoing"]


def test_one_target_within_the_binder_never_itself(api: TestClient) -> None:
    binder = create_binder(api)
    other_binder = create_binder(api)
    cash = create_paper(api, binder["id"], ref="D-1", section="D", title="Cash")
    bank = create_paper(api, binder["id"], ref="D-2", section="D", title="Bank")
    stranger = create_paper(api, other_binder["id"], ref="D-1", section="D", title="Elsewhere")

    assert "exactly one target" in add(api, cash["id"], 422)["detail"]
    assert (
        "exactly one target"
        in add(api, cash["id"], 422, to_wp=bank["id"], to_fs_line="Revenue")["detail"]
    )
    assert "cannot refer to itself" in add(api, cash["id"], 422, to_wp=cash["id"])["detail"]
    assert "in this binder" in add(api, cash["id"], 422, to_wp=stranger["id"])["detail"]
    assert "direction" in add(api, cash["id"], 422, to_wp=bank["id"], direction="up")["detail"]
    assert "attach it first" in add(api, cash["id"], 422, to_vault_doc="f" * 64)["detail"]
    assert add(api, cash["id"], 422, to_fs_line="   ")["detail"]
    assert xrefs_of(api, cash["id"]) == []


def test_a_document_reference_breaks_when_the_document_leaves_the_binder(api: TestClient) -> None:
    binder = create_binder(api, report_date="2026-09-30")
    cash = create_paper(api, binder["id"], ref="D-1", section="D", title="Cash")
    bank = create_paper(api, binder["id"], ref="D-2", section="D", title="Bank")
    with_file = upload(api, bank["id"], "statement.pdf", PDF)
    [attachment] = with_file["attachments"]
    assert attachment["vault_doc_id"]

    paper = add(api, cash["id"], to_vault_doc=attachment["vault_doc_id"], direction="to")
    [ref] = paper["xrefs"]
    assert ref["to_filename"] == "statement.pdf" and ref["broken"] is None
    # Clickable (spec 3E): the reference names the attachment the document is filed as.
    assert ref["to_attachment_id"] == attachment["id"] and ref["to_attachment_ref"] == "D-2"
    # Both directions: the paper that carries the document sees the reference coming in.
    [seen_from_bank] = xrefs_of(api, bank["id"])
    assert seen_from_bank["id"] == ref["id"] and seen_from_bank["outgoing"] is False
    assert seen_from_bank["from_ref"] == "D-1"
    assert ("broken_reference", "D-1") not in blockers(api, binder["id"])

    assert api.delete(f"/api/attachments/{attachment['id']}").status_code == 204
    [ref] = xrefs_of(api, cash["id"])
    assert ref["broken"] == "no paper of this binder carries that document any more"
    assert ref["to_filename"] is None and ref["to_attachment_id"] is None
    assert xrefs_of(api, bank["id"]) == []  # the document left D-2, so did the reference
    found = {
        (b["kind"], b["ref"], b["detail"])
        for b in api.get(f"/api/binders/{binder['id']}/assembly").json()["blockers"]
    }
    assert (
        "broken_reference",
        "D-1",
        f"document {attachment['vault_doc_id']}: no paper of this binder carries that document "
        "any more",
    ) in found
    refused = api.post(f"/api/binders/{binder['id']}/assemble")
    assert refused.status_code == 409 and "broken_reference D-1" in refused.json()["detail"]

    # Re-attaching the same bytes to any paper of the binder mends the reference.
    upload(api, cash["id"], "statement-again.pdf", PDF)
    [ref] = xrefs_of(api, cash["id"])
    assert ref["broken"] is None and ref["to_filename"] == "statement-again.pdf"
    assert ("broken_reference", "D-1") not in blockers(api, binder["id"])

    # Removing the reference itself clears the matter too, while the binder is open.
    assert api.delete(f"/api/xrefs/{ref['id']}").status_code == 204
    assert xrefs_of(api, cash["id"]) == []
    assert api.delete(f"/api/xrefs/{ref['id']}").status_code == 404


def test_a_superseded_target_blocks_assembly_until_the_reference_is_confirmed(
    api: TestClient,
) -> None:
    """Spec 3E: a reference pointing at a superseded paper is surfaced and blocks assembly
    (D36). Papers are never deleted, so "superseded" is a target amended after the reference
    was made; a person confirms the reference against the current version to clear it."""
    binder = create_binder(api, report_date="2026-09-30")
    cash = create_paper(api, binder["id"], ref="D-1", section="D", title="Cash")
    bank = create_paper(api, binder["id"], ref="D-2", section="D", title="Bank")
    full_chain(api, bank["id"])  # D-2 signed off at version 3
    [ref] = add(api, cash["id"], to_wp=bank["id"], direction="to")["xrefs"]
    assert ref["target_amended"] is None and ref["confirmed_by"] is None
    # Nothing to confirm while the target has not changed.
    act_as(api, PREPARER)
    nothing = api.post(f"/api/xrefs/{ref['id']}/confirm")
    assert nothing.status_code == 409 and "nothing to confirm" in nothing.json()["detail"]

    # A content change on the target, then a new prepared version: surfaced, and it blocks.
    edited = api.patch(f"/api/papers/{bank['id']}", json={"result": "Reconciled to the cent"})
    assert edited.status_code == 200, edited.text
    step(api, bank["id"], "prepare")
    [ref] = xrefs_of(api, cash["id"])
    assert ref["target_amended"] == (
        "paper D-2 has been amended since this reference was made (version 3 → 4)"
    )
    assert ref["broken"] is None  # the target is present; it is superseded, not missing
    found = [b for b in assembly_blockers(api, binder["id"]) if b["kind"] == "broken_reference"]
    assert [b["ref"] for b in found] == ["D-1"]
    assert "superseded: paper D-2 has been amended" in found[0]["detail"]
    assert "confirm the reference against the current version, or remove it" in found[0]["detail"]

    # The target's own view of the same reference carries the note too, and a later
    # review or sign-off of the changed content does not alter it.
    step(api, bank["id"], "submit")
    act_as(api, REVIEWER)
    step(api, bank["id"], "review")
    [seen] = xrefs_of(api, bank["id"])
    assert "version 3 → 5" in (seen["target_amended"] or "")

    # Confirming records who, when and which version, and clears the blocker.
    act_as(api, REVIEWER)
    confirmed = api.post(f"/api/xrefs/{ref['id']}/confirm")
    assert confirmed.status_code == 200, confirmed.text
    [ref] = [x for x in confirmed.json()["xrefs"] if x["id"] == ref["id"]]
    assert ref["target_amended"] is None
    assert ref["confirmed_by"] == REVIEWER and ref["confirmed_version"] == 5
    assert ref["confirmed_at"] is not None
    assert ("broken_reference", "D-1") not in blockers(api, binder["id"])

    # A further change after the confirmation supersedes it again, naming the confirmed version.
    act_as(api, PARTNER)
    step(api, bank["id"], "sign-off")  # same content: no change
    assert xrefs_of(api, cash["id"])[0]["target_amended"] is None
    act_as(api, PREPARER)
    api.patch(f"/api/papers/{bank['id']}", json={"result": "Reconciled again"}).raise_for_status()
    step(api, bank["id"], "prepare")
    [ref] = xrefs_of(api, cash["id"])
    assert ref["target_amended"] == (
        "paper D-2 has been amended since this reference was confirmed at version 5 (now version 7)"
    )
    assert ("broken_reference", "D-1") in blockers(api, binder["id"])

    # Removing the reference clears the matter too, while the binder is open.
    assert api.delete(f"/api/xrefs/{ref['id']}").status_code == 204
    assert ("broken_reference", "D-1") not in blockers(api, binder["id"])

    # A reference made to a paper that is still a draft has nothing to be superseded until the
    # target's first prepared content changes: preparing it is not a change, amending it is.
    note = create_paper(api, binder["id"], ref="D-3", section="D", title="Notes")
    [fresh] = [
        x
        for x in add(api, cash["id"], to_wp=note["id"], direction="to")["xrefs"]
        if x["to_ref"] == "D-3"
    ]
    assert fresh["target_amended"] is None
    act_as(api, PREPARER)
    step(api, note["id"], "prepare")
    fresh = next(x for x in xrefs_of(api, cash["id"]) if x["to_ref"] == "D-3")
    assert fresh["target_amended"] is None
    assert ("broken_reference", "D-1") not in blockers(api, binder["id"])
    api.patch(f"/api/papers/{note['id']}", json={"result": "Noted"}).raise_for_status()
    step(api, note["id"], "prepare")
    fresh = next(x for x in xrefs_of(api, cash["id"]) if x["to_ref"] == "D-3")
    assert fresh["target_amended"] == (
        "paper D-3 has been amended since this reference was made (version 1 → 2)"
    )
    assert ("broken_reference", "D-1") in blockers(api, binder["id"])
    api.post(f"/api/xrefs/{fresh['id']}/confirm").raise_for_status()
    assert ("broken_reference", "D-1") not in blockers(api, binder["id"])


def test_only_a_paper_reference_can_be_confirmed_and_never_on_a_purged_binder(
    api: TestClient,
) -> None:
    binder = create_binder(api, report_date="2026-09-30")
    cash = create_paper(api, binder["id"], ref="D-1", section="D", title="Cash")
    [line] = add(api, cash["id"], to_fs_line="BS.A.1", direction="to")["xrefs"]
    refused = api.post(f"/api/xrefs/{line['id']}/confirm")
    assert refused.status_code == 422
    assert "only a reference to a paper can be confirmed" in refused.json()["detail"]
    assert api.post(f"/api/xrefs/{uuid.uuid4()}/confirm").status_code == 404


def test_a_superseded_target_after_assembly_blocks_reassembly_until_confirmed(
    api: TestClient,
) -> None:
    """The amendment of a referenced paper after assembly (spec 3F) supersedes the references
    to it; re-assembly waits for the confirmation, which is allowed on the assembled file."""
    binder = complete_binder(api)
    act_as(api, PREPARER)
    cash = create_paper(api, binder["id"], ref="D-1", section="D", title="Cash")
    bank = create_paper(api, binder["id"], ref="D-2", section="D", title="Bank")
    [ref] = add(api, cash["id"], to_wp=bank["id"], direction="to")["xrefs"]
    full_chain(api, cash["id"])
    full_chain(api, bank["id"])
    act_as(api, PARTNER)
    assert api.post(f"/api/binders/{binder['id']}/assemble").status_code == 200
    amended = api.patch(
        f"/api/papers/{bank['id']}", json={"result": "Revised", "amendment_reason": "review"}
    )
    assert amended.status_code == 200, amended.text
    act_as(api, PREPARER)
    full_chain(api, bank["id"])
    act_as(api, PARTNER)
    kinds = {(b["kind"], b["ref"]) for b in assembly_blockers(api, binder["id"])}
    assert ("broken_reference", "D-1") in kinds
    # Removal is refused after assembly (spec 3F); confirmation is the way through.
    assert api.delete(f"/api/xrefs/{ref['id']}").status_code == 409
    assert api.post(f"/api/xrefs/{ref['id']}/confirm").status_code == 200
    assert ("broken_reference", "D-1") not in blockers(api, binder["id"])
    assert api.post(f"/api/binders/{binder['id']}/assemble").status_code == 200


def assembly_blockers(api: TestClient, binder_id: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = api.get(f"/api/binders/{binder_id}/assembly").json()["blockers"]
    return result


def test_fs_line_references_are_reported_as_not_checked(api: TestClient) -> None:
    binder = create_binder(api)
    cash = create_paper(api, binder["id"], ref="D-1", section="D", title="Cash")
    status = api.get(f"/api/binders/{binder['id']}/assembly").json()
    [line] = status["not_checked"]
    assert "FS lines" in line and "(none in this file)" in line

    paper = add(api, cash["id"], to_fs_line="Cash and cash equivalents", direction="to")
    [ref] = paper["xrefs"]
    assert ref["checked"] is False and ref["broken"] is None
    status = api.get(f"/api/binders/{binder['id']}/assembly").json()
    [line] = status["not_checked"]
    assert "(1 such reference(s) in this file)" in line
    assert ("broken_reference", "D-1") not in {(b["kind"], b["ref"]) for b in status["blockers"]}


def test_references_are_frozen_at_assembly_and_produced_with_the_file(api: TestClient) -> None:
    binder = complete_binder(api)
    papers = {p["ref"]: p for s in binder["sections"] for p in s["papers"]}
    c1, a1 = papers["C-1"], papers["A-1"]
    detail = api.get(f"/api/papers/{c1['id']}").json()
    [csv] = detail["attachments"]
    add(api, a1["id"], to_wp=c1["id"], direction="to")
    add(api, c1["id"], to_vault_doc=csv["vault_doc_id"], direction="to")
    add(api, c1["id"], to_fs_line="Total revenue", direction="from")

    act_as(api, PARTNER)
    assert api.post(f"/api/binders/{binder['id']}/assemble").status_code == 200
    frozen = add(api, a1["id"], 409, to_fs_line="Equity")
    assert "frozen with the file at assembly" in frozen["detail"]
    [a1_ref] = xrefs_of(api, a1["id"])
    locked = api.delete(f"/api/xrefs/{a1_ref['id']}")
    assert locked.status_code == 409 and "nothing is deleted" in locked.json()["detail"]

    produced = api.get(f"/api/binders/{binder['id']}/produce")
    assert produced.status_code == 200
    with zipfile.ZipFile(io.BytesIO(produced.content)) as archive:
        c1_refs = json.loads(archive.read("papers/C-1/cross_references.json"))
        assert {(x["from_ref"], x["to_ref"], x["to_fs_line"], x["outgoing"]) for x in c1_refs} == {
            ("A-1", "C-1", None, False),
            ("C-1", None, None, True),
            ("C-1", None, "Total revenue", False),
        }
        assert all(x["broken"] is None for x in c1_refs)
        assert [x["checked"] for x in c1_refs if x["to_fs_line"]] == [False]
        a1_refs = json.loads(archive.read("papers/A-1/cross_references.json"))
        assert [(x["to_ref"], x["outgoing"]) for x in a1_refs] == [("C-1", True)]
        empty = json.loads(archive.read("papers/B-1/cross_references.json"))
        assert empty == []
        checksums = archive.read("CHECKSUMS.sha256").decode()
        assert "  papers/C-1/cross_references.json\n" in checksums


def test_reference_data_is_not_part_of_the_manifest_hash(api: TestClient) -> None:
    # The manifest hashes content; a reference is a pointer between pieces of content. So the
    # recorded manifest of an already-assembled file still matches after migration 0005.
    binder = complete_binder(api)
    papers = {p["ref"]: p for s in binder["sections"] for p in s["papers"]}
    act_as(api, PARTNER)
    before = api.post(f"/api/binders/{binder['id']}/assemble").json()
    verification = api.get(f"/api/binders/{binder['id']}/verify").json()
    assert verification["ok"] and verification["current_matches_assembled"]
    assert before["assembly_hash"]
    # Nothing in the manifest mentions references.
    assert "xref" not in json.dumps(before["manifest"]).lower()
    assert papers["A-1"]["ref"] == "A-1"
