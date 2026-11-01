"""Stage C (spec 3E, 5.4; D30): FS-line references checked against the linked Spine
version's presentation lines by head_id; a line the version does not have is a named
assembly blocker; the not-checked list empties once lines can be read; the cross-reference
map shows FS line → lead schedule → working paper → source document with broken and amended
links flagged. Against oak_binder_test with the Spine double."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.conftest import PREPARER, REVIEWER, act_as, use_spine
from tests.fake_spine import ENGAGEMENT_ID, LOCKED_VERSION_ID
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


def link(api: TestClient, binder_id: str) -> None:
    response = api.patch(
        f"/api/binders/{binder_id}",
        json={
            "spine_engagement_id": str(ENGAGEMENT_ID),
            "spine_version_id": str(LOCKED_VERSION_ID),
        },
    )
    assert response.status_code == 200, response.text


def status_of(api: TestClient, binder_id: str) -> dict[str, Any]:
    result: dict[str, Any] = api.get(f"/api/binders/{binder_id}/assembly").json()
    return result


def test_fs_lines_come_from_the_linked_version_and_are_required_once_known(api: TestClient) -> None:
    use_spine(api)
    binder = create_binder(api, report_date="2026-09-30")
    cash = create_paper(api, binder["id"], ref="D-1", section="D", title="Cash")

    unlinked = api.get(f"/api/binders/{binder['id']}/fs-lines").json()
    assert unlinked["available"] is False and "not linked" in unlinked["reason"]
    # Unlinked: free text is accepted and reported as not checked.
    free = add(api, cash["id"], to_fs_line="Cash and cash equivalents", direction="to")["xrefs"][0]
    assert free["checked"] is False and free["broken"] is None and free["to_fs_line_label"] is None
    assert "FS lines" in status_of(api, binder["id"])["not_checked"][0]

    link(api, binder["id"])
    lines = api.get(f"/api/binders/{binder['id']}/fs-lines").json()
    assert lines["available"] and lines["version_locked"]
    assert [line["head_id"] for line in lines["lines"]] == ["BS.A.1", "BS.L.1", "PL.R.1"]
    assert lines["lines"][0]["label"] == "Cash and cash equivalents"

    # Linked: a reference must name a line by head_id; the free-text one is now broken.
    refused = add(api, cash["id"], 422, to_fs_line="Cash and cash equivalents", direction="to")
    assert "is not a line of the linked Spine version" in refused["detail"]
    good = next(
        x
        for x in add(api, cash["id"], to_fs_line="BS.A.1", direction="to")["xrefs"]
        if x["to_fs_line"] == "BS.A.1"
    )
    assert good["checked"] is True and good["broken"] is None
    assert good["to_fs_line_label"] == "Cash and cash equivalents"
    stale = next(
        x for x in api.get(f"/api/papers/{cash['id']}/xrefs").json() if x["to_fs_line"] != "BS.A.1"
    )
    assert stale["checked"] is True and stale["broken"] == (
        "not a line of the linked Spine version (it was renamed, removed, or written before "
        "the binder was linked)"
    )

    status = status_of(api, binder["id"])
    assert status["not_checked"] == []  # every reference is checkable now
    broken = [b for b in status["blockers"] if b["kind"] == "broken_reference"]
    assert len(broken) == 1 and broken[0]["ref"] == "D-1"
    # The blocker names the target once, then the reason (the reason does not repeat it).
    assert broken[0]["detail"] == (
        "FS line 'Cash and cash equivalents': not a line of the linked Spine version (it was "
        "renamed, removed, or written before the binder was linked)"
    )
    assert broken[0]["detail"].count("Cash and cash equivalents") == 1
    act_as(api, PARTNER)
    refused = api.post(f"/api/binders/{binder['id']}/assemble")
    assert refused.status_code == 409
    assert refused.json()["detail"].count("Cash and cash equivalents") == 1
    act_as(api, REVIEWER)

    # Removing the stale reference clears the blocker; the good one stays.
    assert api.delete(f"/api/xrefs/{stale['id']}").status_code == 204
    assert not [
        b for b in status_of(api, binder["id"])["blockers"] if b["kind"] == "broken_reference"
    ]


def test_an_unreadable_spine_leaves_fs_lines_unchecked_and_says_why(api: TestClient) -> None:
    spine = use_spine(api)
    binder = create_binder(api)
    cash = create_paper(api, binder["id"], ref="D-1", section="D", title="Cash")
    link(api, binder["id"])
    add(api, cash["id"], to_fs_line="BS.A.1", direction="to")
    spine.fail_with = 503
    lines = api.get(f"/api/binders/{binder['id']}/fs-lines").json()
    assert lines["available"] is False and "could not answer" in lines["reason"]
    [ref] = api.get(f"/api/papers/{cash['id']}/xrefs").json()
    assert ref["checked"] is False and ref["broken"] is None
    status = status_of(api, binder["id"])
    assert any("could not answer" in n for n in status["not_checked"])
    assert not [b for b in status["blockers"] if b["kind"] == "broken_reference"]
    # The Spine being down is itself named, through the Stage B blocker.
    assert any(b["kind"] == "spine_unreachable" for b in status["blockers"])


def test_the_map_shows_the_chain_with_broken_and_amended_links_flagged(api: TestClient) -> None:
    use_spine(api)
    binder = create_binder(api, report_date="2026-09-30")
    link(api, binder["id"])
    lead = create_paper(api, binder["id"], ref="D-L", section="D", title="Cash lead schedule")
    cash = create_paper(api, binder["id"], ref="D-1", section="D", title="Cash and bank")
    petty = create_paper(api, binder["id"], ref="D-2", section="D", title="Petty cash")
    loose = create_paper(api, binder["id"], ref="E-1", section="E", title="Not tied to anything")
    [statement] = upload(api, cash["id"], "statement.pdf", PDF)["attachments"]
    full_chain(api, cash["id"])
    act_as(api, PREPARER)
    step(api, lead["id"], "prepare")  # the lead schedule has a version before anything refers to it

    add(api, lead["id"], to_fs_line="BS.A.1", direction="to")  # the lead schedule ties to the line
    add(api, cash["id"], to_wp=lead["id"], direction="to")  # D-1 refers to the lead schedule
    add(
        api, lead["id"], to_wp=petty["id"], direction="from"
    )  # D-2 refers to the lead, written on D-L
    add(api, cash["id"], to_vault_doc=statement["vault_doc_id"], direction="to")
    add(api, petty["id"], to_fs_line="PL.R.9", direction="to", expected=422)  # not a line: refused
    add(api, loose["id"], to_vault_doc=statement["vault_doc_id"], direction="to")

    # Amend the lead schedule after D-1 referred to it: the map flags the amended target.
    act_as(api, PREPARER)
    api.patch(
        f"/api/papers/{lead['id']}", json={"result": "Agreed to the Spine"}
    ).raise_for_status()
    step(api, lead["id"], "prepare")

    m = api.get(f"/api/binders/{binder['id']}/xref-map").json()
    assert m["available"] is True and m["total_references"] == 5
    assert m["broken"] == 0 and m["amended"] == 1 and m["unchecked"] == 0
    [line] = m["lines"]
    assert line["head_id"] == "BS.A.1" and line["label"] == "Cash and cash equivalents"
    assert line["known"] is True and line["current"] == "1250000.00"
    [lead_node] = line["papers"]
    assert lead_node["ref"] == "D-L" and lead_node["role"] == "lead_schedule"
    assert lead_node["link"]["checked"] is True and lead_node["link"]["broken"] is None
    beneath = {p["ref"]: p for p in lead_node["papers"]}
    assert set(beneath) == {"D-1", "D-2"}
    assert beneath["D-1"]["role"] == "working_paper"
    assert beneath["D-1"]["link"]["amended"] == (
        "paper D-L has been amended since this reference was made (version 1 → 2)"
    )
    [doc] = beneath["D-1"]["documents"]
    assert doc["filename"] == "statement.pdf" and doc["attachment_id"] == statement["id"]
    assert doc["filed_on_ref"] == "D-1" and doc["broken"] is None
    assert beneath["D-2"]["link"]["direction"] == "from"
    assert [p["ref"] for p in m["unattached"]] == ["E-1"]
    assert m["beyond_depth"] == [] and m["max_depth"] == 3
    assert m["unattached"][0]["documents"][0]["filename"] == "statement.pdf"

    # Remove the document: both document references break and the map counts them.
    assert api.delete(f"/api/attachments/{statement['id']}").status_code == 204
    m = api.get(f"/api/binders/{binder['id']}/xref-map").json()
    assert m["broken"] == 2
    doc = (
        m["lines"][0]["papers"][0]["papers"][0]["documents"][0]
        if m["lines"][0]["papers"][0]["papers"][0]["ref"] == "D-1"
        else None
    )
    assert doc is None or "no paper of this binder carries" in doc["broken"]
    act_as(api, REVIEWER)


def test_papers_deeper_than_the_drawn_chain_are_listed_as_part_of_it(api: TestClient) -> None:
    """A paper four or five levels below a line is tied to that line through the papers
    above it; the map lists it apart as 'further down', never as tied to no line."""
    use_spine(api)
    binder = create_binder(api, report_date="2026-09-30")
    link(api, binder["id"])
    lead = create_paper(api, binder["id"], ref="D-L", section="D", title="Lead")
    two = create_paper(api, binder["id"], ref="D-2", section="D", title="Level two")
    three = create_paper(api, binder["id"], ref="D-3", section="D", title="Level three")
    four = create_paper(api, binder["id"], ref="D-4", section="D", title="Level four")
    five = create_paper(api, binder["id"], ref="D-5", section="D", title="Level five")
    loose = create_paper(api, binder["id"], ref="E-1", section="E", title="Tied to nothing")
    [statement] = upload(api, five["id"], "deep.pdf", PDF)["attachments"]
    add(api, lead["id"], to_fs_line="BS.A.1", direction="to")
    add(api, two["id"], to_wp=lead["id"], direction="to")
    add(api, three["id"], to_wp=two["id"], direction="to")
    add(api, four["id"], to_wp=three["id"], direction="to")
    add(api, five["id"], to_wp=four["id"], direction="to")
    add(api, five["id"], to_vault_doc=statement["vault_doc_id"], direction="to")

    m = api.get(f"/api/binders/{binder['id']}/xref-map").json()
    assert m["max_depth"] == 3
    [line] = m["lines"]
    drawn = line["papers"][0]
    assert drawn["ref"] == "D-L" and drawn["papers"][0]["ref"] == "D-2"
    assert drawn["papers"][0]["papers"][0]["ref"] == "D-3"
    assert drawn["papers"][0]["papers"][0]["papers"] == []  # the chain is drawn to depth 3
    assert [p["ref"] for p in m["beyond_depth"]] == ["D-4", "D-5"]
    assert all(p["link"]["checked"] and p["link"]["broken"] is None for p in m["beyond_depth"])
    assert m["beyond_depth"][1]["documents"][0]["filename"] == "deep.pdf"
    assert [p["ref"] for p in m["unattached"]] == ["E-1"]  # only the paper reachable from no line
    assert m["total_references"] == 6 and m["broken"] == 0 and m["unchecked"] == 0

    # Links beyond the drawn depth are still checked: remove the document and it counts.
    assert api.delete(f"/api/attachments/{statement['id']}").status_code == 204
    m = api.get(f"/api/binders/{binder['id']}/xref-map").json()
    assert m["broken"] == 1 and m["beyond_depth"][1]["documents"][0]["broken"]
    assert loose["ref"] in [p["ref"] for p in m["unattached"]]


def _archive_xrefs(data: bytes) -> dict[str, list[dict[str, Any]]]:
    import io
    import json
    import zipfile

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {
            name: json.loads(archive.read(name))
            for name in archive.namelist()
            if name.endswith("cross_references.json")
        }


def _fs_record(records: dict[str, list[dict[str, Any]]], head_id: str) -> dict[str, Any]:
    return next(
        x
        for member in records.values()
        for x in member
        if x["to_fs_line"] == head_id and x["outgoing"]
    )


def test_the_archive_uses_the_lines_verified_at_assembly_not_a_live_spine(
    api: TestClient,
) -> None:
    """Assembly records the lines it verified the references against with the assembled
    event; production reads those, so the archive is the same whether or not the Spine
    answers (D30)."""
    spine = use_spine(api)
    binder = complete_binder(api)
    link(api, binder["id"])
    lead = binder["sections"][0]["papers"][0]
    add(api, lead["id"], to_fs_line="BS.A.1", direction="to")
    act_as(api, PARTNER)
    assembled = api.post(f"/api/binders/{binder['id']}/assemble")
    assert assembled.status_code == 200, assembled.text
    event = [e for e in assembled.json()["events"] if e["kind"] == "assembled"][-1]
    recorded = event["details"]["fs_lines"]
    assert recorded["version_id"] == str(LOCKED_VERSION_ID) and recorded["version_locked"]
    assert [line["head_id"] for line in recorded["lines"]] == ["BS.A.1", "BS.L.1", "PL.R.1"]
    assert recorded["lines"][0]["label"] == "Cash and cash equivalents"
    # The manifest itself is unchanged by the record: the hash still describes the file.
    assert "fs_lines" not in assembled.json()["manifest"]

    reads_before = len([c for c in spine.calls if c.path.endswith("/presentation")])
    with_spine = api.get(f"/api/binders/{binder['id']}/produce")
    assert with_spine.status_code == 200
    spine.fail_with = 503
    without_spine = api.get(f"/api/binders/{binder['id']}/produce")
    assert without_spine.status_code == 200
    spine.time_out = True
    timing_out = api.get(f"/api/binders/{binder['id']}/produce")
    assert timing_out.status_code == 200
    assert len([c for c in spine.calls if c.path.endswith("/presentation")]) == reads_before
    a, b, c = (_archive_xrefs(r.content) for r in (with_spine, without_spine, timing_out))
    assert a == b == c
    record = _fs_record(a, "BS.A.1")
    assert record["from_ref"] == lead["ref"] and record["checked"] is True
    assert record["to_fs_line_label"] == "Cash and cash equivalents" and record["broken"] is None
    assert spine.non_get_calls() == []
    act_as(api, REVIEWER)


def test_a_file_assembled_before_lines_were_recorded_reads_the_spine_as_before(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Compatibility: an assembled event without the record (assembled before Stage C's
    follow-up, or without a readable Spine version) falls back to reading the Spine at
    production, exactly as before; an unlinked binder records no lines at all."""
    from oak_binder.services import produce as produce_service

    spine = use_spine(api)
    unlinked = complete_binder(api)
    act_as(api, PARTNER)
    assembled = api.post(f"/api/binders/{unlinked['id']}/assemble")
    assert assembled.status_code == 200, assembled.text
    event = [e for e in assembled.json()["events"] if e["kind"] == "assembled"][-1]
    assert "fs_lines" not in event["details"] and "spine_version" not in event["details"]

    act_as(api, REVIEWER)
    binder = complete_binder(api)
    link(api, binder["id"])
    lead = binder["sections"][0]["papers"][0]
    add(api, lead["id"], to_fs_line="BS.A.1", direction="to")
    act_as(api, PARTNER)
    assert api.post(f"/api/binders/{binder['id']}/assemble").status_code == 200
    # Pretend the assembled event carries no lines record, as one from before would.
    monkeypatch.setattr(produce_service, "assembled_lines", lambda session, binder: None)
    live = _fs_record(
        _archive_xrefs(api.get(f"/api/binders/{binder['id']}/produce").content), "BS.A.1"
    )
    assert live["checked"] is True and live["to_fs_line_label"] == "Cash and cash equivalents"
    spine.fail_with = 503
    down = _fs_record(
        _archive_xrefs(api.get(f"/api/binders/{binder['id']}/produce").content), "BS.A.1"
    )
    assert down["checked"] is False and down["to_fs_line_label"] is None and down["broken"] is None
    act_as(api, REVIEWER)


def test_the_map_without_a_spine_lists_free_text_lines_as_not_checked(api: TestClient) -> None:
    binder = create_binder(api)
    cash = create_paper(api, binder["id"], ref="D-1", section="D", title="Cash")
    add(api, cash["id"], to_fs_line="Trade receivables", direction="to")
    m = api.get(f"/api/binders/{binder['id']}/xref-map").json()
    assert m["available"] is False and "not linked" in m["reason"]
    [line] = m["lines"]
    assert (
        line["head_id"] == "Trade receivables" and line["known"] is False and line["label"] is None
    )
    assert m["unchecked"] == 1 and m["broken"] == 0
    assert line["papers"][0]["link"]["checked"] is False


def test_map_and_fs_line_reads_of_an_assembled_file_are_access_logged(api: TestClient) -> None:
    use_spine(api)
    binder = complete_binder(api)
    act_as(api, PARTNER)
    api.post(f"/api/binders/{binder['id']}/assemble").raise_for_status()
    act_as(api, "quality.reviewer@firm")
    assert api.get(f"/api/binders/{binder['id']}/xref-map").status_code == 200
    assert api.get(f"/api/binders/{binder['id']}/fs-lines").status_code == 200
    rows = api.get(f"/api/binders/{binder['id']}/assembly").json()["access"]
    assert [r["action"] for r in rows if r["user"] == "quality.reviewer@firm"] == [
        "cross-reference map",
        "FS lines",
        "assembly status",
    ]
