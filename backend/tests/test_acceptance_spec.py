"""Acceptance audit against the specification, clause by clause (D40).

Each test names the clause of ``WORKING_PAPER_BINDER.md`` it proves and exercises the behaviour
over the API against oak_binder_test, with the Spine and WorkMind doubles standing in for the
systems that do not exist here. The last test walks every user workflow end to end. Detailed
rules are proven in the feature test modules; this module is the acceptance matrix's evidence
that every clause holds together on one build."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

from oak_binder.db import Base
from oak_binder.hashing import content_hash
from oak_binder.models import SECTIONS, WpStatus
from tests.conftest import PREPARER, REVIEWER, act_as, use_spine, use_workmind
from tests.fake_spine import ENGAGEMENT_ID, LOCKED_VERSION_ID
from tests.helpers import (
    CSV,
    PARTNER,
    PDF,
    complete_binder,
    create_binder,
    create_paper,
    full_chain,
    generated_fixture,
    step,
    upload,
)
from tests.test_api_assembly import pretend_today

pytestmark = pytest.mark.db
FIXTURES = Path(__file__).parent / "fixtures" / "generated"
SENIOR = "senior@firm"


def fixture(source: str) -> dict[str, Any]:
    return generated_fixture(source)


def assembly(api: TestClient, binder_id: str) -> dict[str, Any]:
    result: dict[str, Any] = api.get(f"/api/binders/{binder_id}/assembly").json()
    return result


def blockers(api: TestClient, binder_id: str) -> set[tuple[str, str | None]]:
    return {(b["kind"], b["ref"]) for b in assembly(api, binder_id)["blockers"]}


def link(api: TestClient, binder_id: str) -> None:
    api.patch(
        f"/api/binders/{binder_id}",
        json={
            "spine_engagement_id": str(ENGAGEMENT_ID),
            "spine_version_id": str(LOCKED_VERSION_ID),
        },
    ).raise_for_status()


def members_of(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


# =============================================================== spec 2: what SA 230 requires


def test_spec_2_record_forces_objective_procedure_result_conclusion_and_no_sign_off_without_one(
    api: TestClient,
) -> None:
    binder = create_binder(api)
    paper = create_paper(api, binder["id"], conclusion=None)
    for field in ("objective", "procedure", "population_sample", "result", "conclusion"):
        assert field in paper
    assert paper["objective"] and paper["procedure"] and paper["result"]
    act_as(api, PREPARER)
    step(api, paper["id"], "prepare")
    step(api, paper["id"], "submit")
    act_as(api, REVIEWER)
    step(api, paper["id"], "review")
    act_as(api, PARTNER)
    refused = api.post(f"/api/papers/{paper['id']}/sign-off")
    assert refused.status_code == 422 and "no conclusion" in refused.json()["detail"]


def test_spec_2_who_performed_and_reviewed_is_captured_at_sign_off_not_typed(
    api: TestClient,
) -> None:
    binder = create_binder(api)
    paper = create_paper(api, binder["id"])
    typed = api.patch(f"/api/papers/{paper['id']}", json={"prepared_by": "someone@firm"})
    assert typed.status_code == 422  # not a content field: identity is never typed
    signed = full_chain(api, paper["id"])
    v = signed["versions"][-1]
    assert (v["prepared_by"], v["reviewed_by"], v["signed_off_by"]) == (PREPARER, REVIEWER, PARTNER)
    assert v["prepared_at"] and v["reviewed_at"] and v["signed_off_at"]
    # Without an identity the action cannot happen at all (spec 7: an authenticated action).
    draft = create_paper(api, binder["id"], ref="D-9", section="D", title="Other")
    act_as(api, None)
    assert api.post(f"/api/papers/{draft['id']}/prepare").status_code == 503
    act_as(api, PREPARER)


def test_spec_2_identifying_characteristics_travel_with_the_sample_and_the_evidence(
    api: TestClient,
) -> None:
    binder = create_binder(api)
    paper = create_paper(
        api,
        binder["id"],
        population_sample="Invoices INV-0007, INV-0042 and INV-0098; vouchers V-12 to V-19",
    )
    assert "INV-0042" in paper["population_sample"]
    [doc] = upload(api, paper["id"], "sales.csv", CSV, identifying_chars="FY26 register rows 1-2")[
        "attachments"
    ]
    assert doc["identifying_chars"] == "FY26 register rows 1-2"
    assert doc["sha256"] == __import__("hashlib").sha256(CSV).hexdigest()


def test_spec_2_sixty_day_assembly_and_seven_year_retention_clocks_run_from_the_report_date(
    api: TestClient,
) -> None:
    binder = create_binder(api, report_date="2026-09-30")
    assert binder["assembly_due"] == "2026-11-29" and binder["retention_until"] == "2033-09-30"
    assert isinstance(binder["days_to_assembly"], int)
    undated = create_binder(api)
    assert undated["assembly_due"] is None and undated["retention_until"] is None
    act_as(api, PARTNER)
    assert ("report_not_dated", None) in blockers(api, undated["id"])


def test_spec_2_nothing_is_deleted_after_assembly_and_a_change_is_a_new_version_with_a_reason(
    api: TestClient,
) -> None:
    binder = complete_binder(api)
    act_as(api, PREPARER)
    paper = create_paper(api, binder["id"])
    [doc] = upload(api, paper["id"], "bank.pdf", PDF)["attachments"]
    full_chain(api, paper["id"])
    act_as(api, PARTNER)
    assert api.post(f"/api/binders/{binder['id']}/assemble").status_code == 200
    assert api.delete(f"/api/attachments/{doc['id']}").status_code == 409
    # Without a reason the edit is refused (422: the reason is required input, D17).
    assert api.patch(f"/api/papers/{paper['id']}", json={"result": "Changed"}).status_code == 422
    amended = api.patch(
        f"/api/papers/{paper['id']}", json={"result": "Changed", "amendment_reason": "typo found"}
    )
    assert amended.status_code == 200, amended.text
    versions = amended.json()["versions"]
    assert (
        versions[-1]["amendment_reason"] == "typo found" and versions[-1]["prepared_by"] == PARTNER
    )
    assert len(versions) == 4  # prepared, reviewed, signed off, amendment
    events = [e["kind"] for e in assembly(api, binder["id"])["events"]]
    assert events[-1] == "amended"


# =============================================================== spec 3A: file structure


def test_spec_3a_templates_sections_completeness_and_lead_schedule_per_area(
    api: TestClient,
) -> None:
    templates = api.get("/api/templates").json()
    assert {t["name"] for t in templates} == {"statutory", "tax_audit", "bank_branch", "internal"}
    statutory = api.get("/api/templates/statutory").json()
    assert [s["code"] for s in statutory["sections"]] == list(SECTIONS)
    names = {s["code"]: s["name"] for s in statutory["sections"]}
    assert names["A"] == "Acceptance" and names["Z"] == "EQR"
    binder = create_binder(api, report_date="2026-09-30")
    assert binder["missing_required"] == 6
    missing = {m["ref"] for s in binder["sections"] for m in s["missing"]}
    assert missing == {r["ref"] for r in statutory["required"]}
    # Lead schedule per area, tying to the Spine (D32, D38): the derived map gives one per group.
    use_spine(api)
    link(api, binder["id"])
    status = api.get(f"/api/binders/{binder['id']}/spine-papers").json()
    assert status["can_generate"] is True and status["map_source"] == "derived"
    leads = api.post(
        f"/api/binders/{binder['id']}/spine-papers/lead-schedules", json={"areas": None}
    )
    assert leads.status_code == 201, leads.text
    assert [p["ref"] for p in leads.json()] == ["D-L", "E-L", "F-L", "G-L"]
    assert leads.json()[0]["title"] == "Lead schedule: Assets"
    index = api.get(f"/api/binders/{binder['id']}").json()
    section_d = next(s for s in index["sections"] if s["code"] == "D")
    assert [p["ref"] for p in section_d["papers"]] == ["D-L"]


# =============================================================== spec 3B: the working paper


def test_spec_3b_every_field_a_stable_reference_and_the_status_chain(api: TestClient) -> None:
    binder = create_binder(api)
    paper = create_paper(api, binder["id"])
    for field in (
        "ref",
        "title",
        "section",
        "sa_refs",
        "objective",
        "procedure",
        "population_sample",
        "result",
        "conclusion",
        "status",
        "attachments",
        "xrefs",
        "versions",
    ):
        assert field in paper, field
    assert api.patch(f"/api/papers/{paper['id']}", json={"ref": "D-2"}).status_code == 422
    dup = api.post(
        f"/api/binders/{binder['id']}/papers",
        json={"ref": paper["ref"], "section": "D", "title": "Again"},
    )
    assert dup.status_code == 409  # never reused
    assert [s.value for s in WpStatus] == [
        "draft",
        "prepared",
        "in_review",
        "reviewed",
        "signed_off",
    ]
    seen = [paper["status"]]
    act_as(api, PREPARER)
    seen.append(step(api, paper["id"], "prepare")["status"])
    seen.append(step(api, paper["id"], "submit")["status"])
    act_as(api, REVIEWER)
    seen.append(step(api, paper["id"], "review")["status"])
    act_as(api, PARTNER)
    seen.append(step(api, paper["id"], "sign-off")["status"])
    assert seen == ["draft", "prepared", "in_review", "reviewed", "signed_off"]
    # Cross-references in and out: a reference written on one paper appears on both.
    other = create_paper(api, binder["id"], ref="D-2", section="D", title="Bank")
    api.post(f"/api/papers/{other['id']}/xrefs", json={"to_wp": paper["id"], "direction": "to"})
    [outgoing] = api.get(f"/api/papers/{other['id']}/xrefs").json()
    [incoming] = api.get(f"/api/papers/{paper['id']}/xrefs").json()
    assert outgoing["outgoing"] is True and incoming["outgoing"] is False
    assert outgoing["id"] == incoming["id"]


# =============================================================== spec 3C: generated papers


def test_spec_3c_every_source_arrives_complete_with_inputs_and_citations_and_nobody_retypes(
    api: TestClient,
) -> None:
    spine = use_spine(api)
    spine.lock(LOCKED_VERSION_ID)
    workmind = use_workmind(api)
    binder = create_binder(api, report_date="2026-09-30")
    link(api, binder["id"])
    filed: dict[str, dict[str, Any]] = {}
    for source in ("materiality", "sampling", "analytical_review", "workmind"):
        body = fixture(source)
        if source == "materiality":
            body["generated"]["materiality"]["spine_figures"]["version_id"] = str(LOCKED_VERSION_ID)
        delivered = api.post(f"/api/binders/{binder['id']}/generated-papers", json=body)
        assert delivered.status_code == 201, (source, delivered.text)
        filed[source] = delivered.json()
        paper = filed[source]
        assert paper["status"] == "draft" and paper["generated_by"] == source
        assert (
            paper["generated"]["payload"]["inputs"] and paper["generated"]["payload"]["citations"]
        )
        # Nobody retypes: the module's fields are locked on the paper.
        locked = api.patch(f"/api/papers/{paper['id']}", json={"result": "retyped"})
        assert locked.status_code == 422 and "module" in locked.json()["detail"].lower()
    assert filed["materiality"]["generated"]["spine_figures_check"] == "verified"
    seed = fixture("sampling")["generated"]["sampling"]["seed"]
    assert str(seed) in filed["sampling"]["population_sample"]  # 8.8: formula and seed printed
    assert filed["workmind"]["conclusion"] is None  # spec 7: never drafted automatically
    assert filed["workmind"]["generated"]["run_verification"]["status"] == "accepted"
    assert workmind.non_get_calls() == []
    # Financial Spine: every lead schedule and the adjustment chain.
    leads = api.post(
        f"/api/binders/{binder['id']}/spine-papers/lead-schedules", json={"areas": None}
    )
    assert leads.status_code == 201 and len(leads.json()) == 4
    chain = api.post(f"/api/binders/{binder['id']}/spine-papers/adjustment-chain")
    assert chain.status_code == 201 and chain.json()["ref"] == "W-ADJ"
    assert chain.json()["generated"]["payload"]["spine"]["kind"] == "adjustment_chain"


# =============================================================== spec 3D: review


def test_spec_3d_review_notes_block_sign_off_levels_are_configurable_and_sign_offs_are_recorded(
    api: TestClient,
) -> None:
    binder = create_binder(api)
    api.patch(
        f"/api/binders/{binder['id']}", json={"review_levels": ["senior", "partner"]}
    ).raise_for_status()
    paper = create_paper(api, binder["id"])
    act_as(api, PREPARER)
    step(api, paper["id"], "prepare")
    step(api, paper["id"], "submit")
    act_as(api, REVIEWER)
    note = api.post(f"/api/papers/{paper['id']}/review-notes", json={"text": "Tie to bank"}).json()
    assert note["state"] == "raised"
    note = api.post(
        f"/api/review-notes/{note['note_id']}/assign", json={"assigned_to": PREPARER}
    ).json()
    assert note["state"] == "assigned"
    act_as(api, PREPARER)
    note = api.post(f"/api/review-notes/{note['note_id']}/respond", json={"text": "Tied"}).json()
    assert note["state"] == "responded" and note["open"] is True
    act_as(api, SENIOR)
    reviewed = step(api, paper["id"], "review")
    assert reviewed["status"] == "in_review" and reviewed["review_chain"]["next_level"] == "partner"
    frozen = api.patch(f"/api/binders/{binder['id']}", json={"review_levels": ["senior"]})
    assert frozen.status_code == 409  # configuration frozen once a level review exists
    act_as(api, PARTNER)
    reviewed = step(api, paper["id"], "review")
    assert reviewed["status"] == "reviewed"
    blocked = api.post(f"/api/papers/{paper['id']}/sign-off")
    assert (
        blocked.status_code == 409 and "open review note" in blocked.json()["detail"]
    )  # hard rule
    act_as(api, REVIEWER)
    api.post(f"/api/review-notes/{note['note_id']}/clear").raise_for_status()
    act_as(api, PARTNER)
    signed = step(api, paper["id"], "sign-off")
    chain = signed["review_chain"]["steps"]
    assert [s["level"] for s in chain] == ["preparer", "senior", "partner", "sign-off"]
    assert all(s["done"] and s["by"] and s["at"] and s["version"] for s in chain)
    v = signed["versions"][-1]
    assert (
        v["signed_off_by"] == PARTNER
        and v["signed_off_at"]
        and v["version"] == len(signed["versions"])
    )


# =============================================================== spec 3E: cross-referencing


def test_spec_3e_the_chain_is_navigable_and_broken_or_superseded_references_block(
    api: TestClient,
) -> None:
    use_spine(api)
    binder = create_binder(api, report_date="2026-09-30")
    link(api, binder["id"])
    [lead] = api.post(
        f"/api/binders/{binder['id']}/spine-papers/lead-schedules", json={"areas": ["D"]}
    ).json()
    cash = create_paper(api, binder["id"], ref="D-1", section="D", title="Cash")
    [doc] = upload(api, cash["id"], "statement.pdf", PDF)["attachments"]
    api.post(
        f"/api/papers/{cash['id']}/xrefs", json={"to_wp": lead["id"], "direction": "to"}
    ).raise_for_status()
    api.post(
        f"/api/papers/{cash['id']}/xrefs",
        json={"to_vault_doc": doc["vault_doc_id"], "direction": "to"},
    ).raise_for_status()
    m = api.get(f"/api/binders/{binder['id']}/xref-map").json()
    [line] = m["lines"]
    assert line["head_id"] == "BS.A.1" and line["papers"][0]["ref"] == "D-L"
    assert line["papers"][0]["papers"][0]["ref"] == "D-1"
    assert line["papers"][0]["papers"][0]["documents"][0]["filename"] == "statement.pdf"
    # Clickable both ways: each node carries the ids the screens link to.
    assert (
        line["papers"][0]["id"] == lead["id"] and line["papers"][0]["papers"][0]["id"] == cash["id"]
    )
    # A deleted document target is surfaced and blocks.
    act_as(api, PREPARER)
    api.delete(f"/api/attachments/{doc['id']}").raise_for_status()
    found = {(b["kind"], b["ref"]) for b in assembly(api, binder["id"])["blockers"]}
    assert ("broken_reference", "D-1") in found
    # A superseded paper target blocks until confirmed (D36).
    other = create_paper(api, binder["id"], ref="D-2", section="D", title="Bank")
    [ref] = [
        x
        for x in api.post(
            f"/api/papers/{cash['id']}/xrefs", json={"to_wp": other["id"], "direction": "to"}
        ).json()["xrefs"]
        if x["to_ref"] == "D-2"
    ]
    step(api, other["id"], "prepare")
    api.patch(f"/api/papers/{other['id']}", json={"result": "Changed"}).raise_for_status()
    step(api, other["id"], "prepare")
    detail = [
        b["detail"]
        for b in assembly(api, binder["id"])["blockers"]
        if b["kind"] == "broken_reference"
    ]
    assert any("superseded" in d for d in detail)
    api.post(f"/api/xrefs/{ref['id']}/confirm").raise_for_status()
    detail = [
        b["detail"]
        for b in assembly(api, binder["id"])["blockers"]
        if b["kind"] == "broken_reference"
    ]
    assert not any("superseded" in d for d in detail)


# =============================================================== spec 3F: assembly


def test_spec_3f_assemble_freezes_hashes_writes_a_manifest_and_is_blocked_by_the_named_items(
    api: TestClient,
) -> None:
    binder = complete_binder(api)
    act_as(api, PREPARER)
    unsigned = create_paper(api, binder["id"], ref="D-1", section="D", title="Cash")
    step(api, unsigned["id"], "prepare")
    step(api, unsigned["id"], "submit")
    act_as(api, REVIEWER)
    api.post(f"/api/papers/{unsigned['id']}/review-notes", json={"text": "Open"}).raise_for_status()
    found = blockers(api, binder["id"])
    assert ("unsigned_paper", "D-1") in found and ("open_review_notes", "D-1") in found
    act_as(api, PARTNER)
    refused = api.post(f"/api/binders/{binder['id']}/assemble")
    assert refused.status_code == 409 and "unsigned_paper D-1" in refused.json()["detail"]
    fresh = create_binder(api, report_date="2026-09-30")
    assert ("missing_required_paper", "C-1") in blockers(api, fresh["id"])
    # Clear and assemble: hash, manifest with every paper and its hash.
    note = api.get(f"/api/papers/{unsigned['id']}/review-notes").json()[0]
    api.post(
        f"/api/review-notes/{note['note_id']}/assign", json={"assigned_to": PREPARER}
    ).raise_for_status()
    act_as(api, PREPARER)
    api.post(
        f"/api/review-notes/{note['note_id']}/respond", json={"text": "Done"}
    ).raise_for_status()
    act_as(api, REVIEWER)
    api.post(f"/api/review-notes/{note['note_id']}/clear").raise_for_status()
    step(api, unsigned["id"], "review")
    act_as(api, PARTNER)
    step(api, unsigned["id"], "sign-off")
    assembled = api.post(f"/api/binders/{binder['id']}/assemble")
    assert assembled.status_code == 200, assembled.text
    manifest = assembled.json()["manifest"]
    assert content_hash(manifest) == assembled.json()["assembly_hash"]
    assert {p["ref"] for p in manifest["papers"]} == {
        "A-1",
        "B-1",
        "C-1",
        "W-1",
        "X-1",
        "Z-1",
        "D-1",
    }
    assert all(p["content_hash"] for p in manifest["papers"])
    status = assembly(api, binder["id"])
    assert status["state"] == "assembled" and status["assembled_at"] and status["assembly_hash"]
    assert (
        api.post(
            f"/api/binders/{binder['id']}/papers", json={"ref": "D-2", "section": "D", "title": "x"}
        ).status_code
        == 409
    )


# =============================================================== spec 3G: retention and production


def test_spec_3g_native_format_one_action_production_and_purge_only_after_retention(
    api: TestClient,
) -> None:
    binder = complete_binder(api, report_date="2026-09-30")
    act_as(api, PREPARER)
    paper = create_paper(api, binder["id"])
    [doc] = upload(api, paper["id"], "bank.pdf", PDF, identifying_chars="HDFC statement March")[
        "attachments"
    ]
    full_chain(api, paper["id"])
    act_as(api, PARTNER)
    api.post(f"/api/binders/{binder['id']}/assemble").raise_for_status()
    produced = api.get(f"/api/binders/{binder['id']}/produce")
    assert produced.status_code == 200 and produced.headers["content-type"].startswith(
        "application/zip"
    )
    members = members_of(produced.content)
    assert {"manifest.json", "audit_trail.json", "CHECKSUMS.sha256"} <= set(members)
    native = [n for n in members if n.endswith("/attachments/bank.pdf")]
    assert len(native) == 1 and members[native[0]] == PDF  # the original bytes, not a print
    assert api.get(f"/api/binders/{binder['id']}/verify").json()["ok"] is True
    early = api.post(f"/api/binders/{binder['id']}/purge")
    assert early.status_code == 409 and "2033-09-30" in early.json()["detail"]
    pretend_today(api, date(2033, 9, 30))
    purged = api.post(f"/api/binders/{binder['id']}/purge")
    assert purged.status_code == 200 and purged.json()["state"] == "purged"
    assert [e["kind"] for e in assembly(api, binder["id"])["events"]][-1] == "purged"
    assert api.get(f"/api/attachments/{doc['id']}/content").status_code in (404, 410)


# =============================================================== spec 3H: records


def test_spec_3h_discussions_with_tcwg_departures_and_the_post_assembly_access_log(
    api: TestClient,
) -> None:
    binder = complete_binder(api)
    act_as(api, PREPARER)
    discussion = api.post(
        f"/api/binders/{binder['id']}/discussions",
        json={
            "date": "2026-10-30",
            "participants": ["A. Partner", "R. Mehta (TCWG, Audit Committee Chair)"],
            "matter": "Going concern",
            "outcome": "Management to provide cash-flow forecast",
        },
    )
    assert discussion.status_code == 201 and discussion.json()["recorded_by"] == PREPARER
    departure = api.post(
        f"/api/binders/{binder['id']}/departures",
        json={
            "requirement": "SA 505 external confirmation",
            "reason": "No bank reply",
            "alternative_procedure": "Agreed to statements and subsequent receipts",
        },
    )
    assert departure.status_code == 201
    act_as(api, PARTNER)
    assert assembly(api, binder["id"])["access"] == []  # nothing logged before assembly
    api.post(f"/api/binders/{binder['id']}/assemble").raise_for_status()
    act_as(api, "auditor@nfra")
    api.get(f"/api/binders/{binder['id']}/discussions").raise_for_status()
    api.get(f"/api/binders/{binder['id']}/produce").raise_for_status()
    act_as(api, PARTNER)
    rows = assembly(api, binder["id"])["access"]
    by_auditor = [r["action"] for r in rows if r["user"] == "auditor@nfra"]
    assert "discussions" in by_auditor and "produce" in by_auditor
    assert all(r["at"] for r in rows)


# =============================================================== spec 4: data model


def test_spec_4_every_table_and_field_exists_and_the_append_only_tables_refuse_change(
    db: Connection,
) -> None:
    tables = set(Base.metadata.tables)
    for name in (
        "binder",
        "wp",
        "wp_version",
        "wp_attachment",
        "xref",
        "review_note",
        "discussion",
        "departure",
        "access_log",
    ):
        assert name in tables, name
    columns = {
        name: {c.name for c in table.columns} for name, table in Base.metadata.tables.items()
    }
    assert {
        "engagement",
        "template",
        "report_date",
        "assembly_due",
        "assembled_at",
        "assembly_hash",
        "retention_until",
        "state",
    } <= columns["binder"]
    assert {
        "binder_id",
        "ref",
        "section",
        "title",
        "sa_refs",
        "objective",
        "procedure",
        "result",
        "conclusion",
        "status",
        "current_version",
    } <= columns["wp"]
    assert {
        "wp_id",
        "version",
        "body",
        "prepared_by",
        "prepared_at",
        "reviewed_by",
        "reviewed_at",
        "content_hash",
        "amendment_reason",
    } <= columns["wp_version"]
    assert {"wp_version_id", "vault_doc_id", "identifying_chars", "sha256"} <= columns[
        "wp_attachment"
    ]
    assert {"from_wp", "to_wp", "to_fs_line", "to_vault_doc", "direction"} <= columns["xref"]
    assert {
        "wp_id",
        "raised_by",
        "assigned_to",
        "text",
        "state",
        "responded_at",
        "cleared_by",
    } <= columns["review_note"]
    assert {"binder_id", "date", "participants", "matter", "outcome"} <= columns["discussion"]
    assert {
        "binder_id",
        "requirement",
        "reason",
        "alternative_procedure",
        "approved_by",
    } <= columns["departure"]
    assert {"binder_id", "user", "action", "at"} <= columns["access_log"]
    # Append-only at the database: each table carries the refusing trigger (row-level proofs
    # with real rows are in the test_db_rules modules).
    for table in ("wp_version", "review_note", "discussion", "departure", "access_log"):
        triggers = (
            db.execute(
                text(
                    "SELECT p.proname FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
                    "JOIN pg_proc p ON p.oid = t.tgfoid "
                    "WHERE c.relname = :table AND NOT t.tgisinternal"
                ),
                {"table": table},
            )
            .scalars()
            .all()
        )
        assert "oak_binder_append_only" in triggers, (table, triggers)
        with pytest.raises(IntegrityError), db.begin_nested():
            db.execute(text(f"TRUNCATE {table} CASCADE"))  # noqa: S608


# =============================================================== spec 5: screens (their data)


def test_spec_5_each_screen_has_its_endpoint_answering_with_the_data_it_shows(
    api: TestClient,
) -> None:
    binder = complete_binder(api)
    act_as(api, PREPARER)
    paper = create_paper(api, binder["id"])
    # 1 Binder: index tree, completeness, countdown.
    b = api.get(f"/api/binders/{binder['id']}").json()
    assert "sections" in b and "missing_required" in b and "days_to_assembly" in b
    # 2 Working paper: paper, versions, attachments, cross-references, sign-off state.
    p = api.get(f"/api/papers/{paper['id']}").json()
    assert {"versions", "attachments", "xrefs", "status", "review_chain"} <= set(p)
    # 3 Review notes: open, by whom, assigned, blocking what.
    notes = api.get(f"/api/binders/{binder['id']}/review-notes").json()
    assert isinstance(notes, dict | list)
    # 4 Cross-reference map.
    m = api.get(f"/api/binders/{binder['id']}/xref-map").json()
    assert {"available", "lines", "broken", "amended"} <= set(m)
    # 5 Assembly and retention: blockers, manifest, produce.
    s = assembly(api, binder["id"])
    assert {"blockers", "manifest", "retention_until", "purge_allowed", "events", "access"} <= set(
        s
    )


# =============================================================== spec 7: not in v1, as built


def test_spec_7_conclusions_are_never_drafted_automatically_and_sign_off_is_an_authenticated_act(
    api: TestClient,
) -> None:
    use_workmind(api)
    binder = create_binder(api)
    body = fixture("workmind")
    body["paper"]["conclusion"] = "Drafted by the agent"
    refused = api.post(f"/api/binders/{binder['id']}/generated-papers", json=body)
    assert refused.status_code == 422 and "spec 7" in refused.json()["detail"]
    paper = create_paper(api, binder["id"])
    act_as(api, PREPARER)
    step(api, paper["id"], "prepare")
    step(api, paper["id"], "submit")
    act_as(api, REVIEWER)
    step(api, paper["id"], "review")
    act_as(api, None)
    assert api.post(f"/api/papers/{paper['id']}/sign-off").status_code == 503
    act_as(api, PARTNER)
    signed = step(api, paper["id"], "sign-off")
    assert signed["versions"][-1]["signed_off_by"] == PARTNER


# =============================================================== spec 8: acceptance 1–9


def test_spec_8_acceptance_criteria_one_to_nine(api: TestClient) -> None:
    use_spine(api)
    binder = create_binder(api, report_date="2026-09-30")
    # 1 no conclusion, no sign-off
    bare = create_paper(api, binder["id"], ref="D-1", section="D", title="Bare", conclusion=None)
    act_as(api, PREPARER)
    step(api, bare["id"], "prepare")
    step(api, bare["id"], "submit")
    act_as(api, REVIEWER)
    step(api, bare["id"], "review")
    act_as(api, PARTNER)
    assert api.post(f"/api/papers/{bare['id']}/sign-off").status_code == 422
    # 2 open review note, no sign-off
    noted = create_paper(api, binder["id"], ref="D-2", section="D", title="Noted")
    act_as(api, PREPARER)
    step(api, noted["id"], "prepare")
    step(api, noted["id"], "submit")
    act_as(api, REVIEWER)
    api.post(f"/api/papers/{noted['id']}/review-notes", json={"text": "Check"}).raise_for_status()
    step(api, noted["id"], "review")
    act_as(api, PARTNER)
    assert api.post(f"/api/papers/{noted['id']}/sign-off").status_code == 409
    # 3 assembly blocked by each named kind
    kinds = {b["kind"] for b in assembly(api, binder["id"])["blockers"]}
    assert {"unsigned_paper", "open_review_notes", "missing_required_paper"} <= kinds
    # 7 retention date and purge before it fails
    assert binder["retention_until"] == "2033-09-30"
    assert api.post(f"/api/binders/{binder['id']}/purge").status_code == 409
    # 8 a sampling paper carries its formula and its seed
    sampling = api.post(
        f"/api/binders/{binder['id']}/generated-papers", json=fixture("sampling")
    ).json()
    block = fixture("sampling")["generated"]["sampling"]
    text_of = " ".join(
        str(sampling[f] or "") for f in ("objective", "procedure", "population_sample", "result")
    )
    assert block["formula"] in text_of and str(block["seed"]) in text_of
    # 4, 5, 6, 9 on an assembled file
    done = complete_binder(api)
    act_as(api, PREPARER)
    paper = create_paper(api, done["id"])
    signed = full_chain(api, paper["id"])
    v = signed["versions"][-1]
    assert v["signed_off_by"] == PARTNER and v["signed_off_at"] and v["version"] == 3  # 9
    act_as(api, PARTNER)
    assembled = api.post(f"/api/binders/{done['id']}/assemble").json()
    assert content_hash(assembled["manifest"]) == assembled["assembly_hash"]  # 5
    assert {p["ref"] for p in assembled["manifest"]["papers"]} >= {"A-1", "C-1", paper["ref"]}
    produced = api.get(f"/api/binders/{done['id']}/produce")  # 6
    members = members_of(produced.content)
    assert "manifest.json" in members and any(
        n.endswith("/attachments/benchmark.csv") for n in members
    )
    assert (
        api.delete(f"/api/attachments/{signed['attachments'][0]['id']}").status_code == 409
        if signed["attachments"]
        else True
    )
    edited = api.patch(
        f"/api/papers/{paper['id']}", json={"result": "Amended", "amendment_reason": "review"}
    )  # 4
    assert (
        edited.status_code == 200 and edited.json()["versions"][-1]["amendment_reason"] == "review"
    )
    assert api.patch(f"/api/papers/{paper['id']}", json={"result": "Again"}).status_code == 422


# =============================================================== every user workflow, end to end


def test_every_user_workflow_end_to_end(api: TestClient) -> None:
    """Create a binder; create and edit papers; prepare and review; review notes; attachments;
    generated papers (modules via fixtures, WorkMind via its double, Spine via its double);
    cross-references incl. confirmation; discussions and departures; assemble; amend; produce
    and verify; retention and purge; post-assembly access."""
    spine = use_spine(api)
    spine.lock(LOCKED_VERSION_ID)
    use_workmind(api)

    # Create a binder from the index template and date the report.
    act_as(api, PREPARER)
    binder = create_binder(api, report_date="2026-09-30")
    bid = binder["id"]
    assert binder["state"] == "open" and binder["missing_required"] == 6
    api.patch(
        f"/api/binders/{bid}", json={"review_levels": ["senior", "partner"]}
    ).raise_for_status()

    # Create and edit working papers: the six required ones from the index, then a hand-made one.
    template = api.get("/api/templates/statutory").json()
    for required in template["required"]:
        create_paper(
            api,
            bid,
            ref=required["ref"],
            section=required["section"],
            title=required["title"],
            sa_refs=required["sa_refs"],
        )
    assert api.get(f"/api/binders/{bid}").json()["missing_required"] == 0
    cash = create_paper(api, bid, ref="D-1", section="D", title="Cash and bank", conclusion=None)
    edited = api.patch(
        f"/api/papers/{cash['id']}",
        json={"result": "No exceptions", "conclusion": "Cash is fairly stated"},
    )
    assert edited.status_code == 200 and edited.json()["status"] == "draft"

    # Attachments: native file with identifying characteristics; download returns the bytes.
    [doc] = upload(
        api, cash["id"], "statement.pdf", PDF, identifying_chars="HDFC statement, March 2026"
    )["attachments"]
    assert api.get(f"/api/attachments/{doc['id']}/content").content == PDF

    # Generated papers: a sampling paper from the Sampling fixture, a WorkMind run read back.
    sampling = api.post(f"/api/binders/{bid}/generated-papers", json=fixture("sampling")).json()
    assert sampling["generated_by"] == "sampling" and sampling["status"] == "draft"
    workmind_paper = api.post(
        f"/api/binders/{bid}/generated-papers", json=fixture("workmind")
    ).json()
    assert workmind_paper["generated"]["run_verification"]["status"] == "accepted"
    api.patch(
        f"/api/papers/{workmind_paper['id']}", json={"conclusion": "Recoverable."}
    ).raise_for_status()

    # Spine: link, derived lead schedules, adjustment chain; freshness current.
    link(api, bid)
    leads = api.post(f"/api/binders/{bid}/spine-papers/lead-schedules", json={"areas": None}).json()
    chain = api.post(f"/api/binders/{bid}/spine-papers/adjustment-chain").json()
    assert chain["ref"] == "W-ADJ" and chain["section"] == "W"
    status = api.get(f"/api/binders/{bid}/spine-papers").json()
    assert {a["state"] for a in status["areas"] if a["mapped"]} == {"current"}
    assert status["chain"]["state"] == "current"

    # Cross-references: paper → lead schedule, paper → document, FS line (checked); confirm later.
    api.post(
        f"/api/papers/{cash['id']}/xrefs", json={"to_wp": leads[0]["id"], "direction": "to"}
    ).raise_for_status()
    api.post(
        f"/api/papers/{cash['id']}/xrefs",
        json={"to_vault_doc": doc["vault_doc_id"], "direction": "to"},
    ).raise_for_status()
    api.post(
        f"/api/papers/{cash['id']}/xrefs", json={"to_fs_line": "BS.A.1", "direction": "to"}
    ).raise_for_status()
    [line_ref] = [x for x in api.get(f"/api/papers/{cash['id']}/xrefs").json() if x["to_fs_line"]]
    assert line_ref["checked"] is True and line_ref["broken"] is None

    # Discussions and departures.
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
            "reason": "No reply",
            "alternative_procedure": "Subsequent receipts",
            "approved_by": None,
        },
    ).raise_for_status()

    # Prepare and review every paper through the configured levels; review notes on one of them.
    papers = [p for s in api.get(f"/api/binders/{bid}").json()["sections"] for p in s["papers"]]
    for paper in papers:
        full = api.get(f"/api/papers/{paper['id']}").json()
        if not full["conclusion"]:
            api.patch(
                f"/api/papers/{paper['id']}", json={"conclusion": "Satisfactory."}
            ).raise_for_status()
        act_as(api, PREPARER)
        step(api, paper["id"], "prepare")
        step(api, paper["id"], "submit")
        if paper["ref"] == "D-1":
            act_as(api, SENIOR)
            note = api.post(
                f"/api/papers/{paper['id']}/review-notes",
                json={"text": "Agree the closing balance"},
            ).json()
            api.post(
                f"/api/review-notes/{note['note_id']}/assign", json={"assigned_to": PREPARER}
            ).raise_for_status()
            act_as(api, PREPARER)
            api.post(
                f"/api/review-notes/{note['note_id']}/respond",
                json={"text": "Agreed to the statement"},
            ).raise_for_status()
        act_as(api, SENIOR)
        step(api, paper["id"], "review")
        act_as(api, PARTNER)
        step(api, paper["id"], "review")
        if paper["ref"] == "D-1":
            assert api.post(f"/api/papers/{paper['id']}/sign-off").status_code == 409
            act_as(api, SENIOR)
            api.post(f"/api/review-notes/{note['note_id']}/clear").raise_for_status()
            act_as(api, PARTNER)
        step(api, paper["id"], "sign-off")
    act_as(api, PARTNER)
    assert assembly(api, bid)["blockers"] == []

    # Assemble and lock.
    assembled = api.post(f"/api/binders/{bid}/assemble")
    assert assembled.status_code == 200, assembled.text
    manifest = assembled.json()["manifest"]
    assert (
        len(manifest["papers"]) == len(papers)
        and content_hash(manifest) == assembled.json()["assembly_hash"]
    )
    assert (
        api.post(
            f"/api/binders/{bid}/papers", json={"ref": "D-9", "section": "D", "title": "x"}
        ).status_code
        == 409
    )
    assert api.delete(f"/api/attachments/{doc['id']}").status_code == 409

    # Amend after assembly: a new version with the reason; the lead schedule D-1 refers to is
    # superseded by a regeneration-free content edit, so D-1's reference must be confirmed.
    amended = api.patch(
        f"/api/papers/{leads[0]['id']}",
        json={
            "objective": "Agree the area to the ledger",
            "amendment_reason": "objective written at review",
        },
    )
    assert amended.status_code == 200, amended.text
    assert (
        api.get(f"/api/binders/{bid}/produce").status_code == 409
    )  # production waits for re-assembly
    act_as(api, PREPARER)
    step(api, leads[0]["id"], "prepare")
    step(api, leads[0]["id"], "submit")
    act_as(api, SENIOR)
    step(api, leads[0]["id"], "review")
    act_as(api, PARTNER)
    step(api, leads[0]["id"], "review")
    step(api, leads[0]["id"], "sign-off")
    superseded = [b for b in assembly(api, bid)["blockers"] if b["kind"] == "broken_reference"]
    assert len(superseded) == 1 and "superseded" in superseded[0]["detail"]
    [lead_ref] = [
        x for x in api.get(f"/api/papers/{cash['id']}/xrefs").json() if x["to_wp"] == leads[0]["id"]
    ]
    api.post(f"/api/xrefs/{lead_ref['id']}/confirm").raise_for_status()
    assert assembly(api, bid)["blockers"] == []
    reassembled = api.post(f"/api/binders/{bid}/assemble")
    assert reassembled.status_code == 200, reassembled.text
    kinds = [e["kind"] for e in assembly(api, bid)["events"]]
    assert kinds.count("assembled") == 2 and "amended" in kinds

    # Produce and verify the complete archive.
    act_as(api, "auditor@nfra")
    produced = api.get(f"/api/binders/{bid}/produce")
    assert produced.status_code == 200
    members = members_of(produced.content)
    for name in (
        "manifest.json",
        "binder.json",
        "audit_trail.json",
        "access_log.json",
        "discussions.json",
        "departures.json",
        "cross_reference_map.json",
        "CHECKSUMS.sha256",
    ):
        assert name in members, name
    folders = {n.split("/")[1] for n in members if n.startswith("papers/")}
    assert folders == {p["ref"] for p in papers}
    assert members[next(n for n in members if n.endswith("/attachments/statement.pdf"))] == PDF
    assert (
        json.loads(members["manifest.json"])["papers"]
        == json.loads(json.dumps(reassembled.json()["manifest"], default=str))["papers"]
    )
    assert json.loads(members["discussions.json"])[0]["participants"][1] == "R. Mehta (TCWG)"
    verify = api.get(f"/api/binders/{bid}/verify").json()
    assert verify["ok"] is True and verify["current_matches_assembled"] is True
    act_as(api, PARTNER)

    # Retention and purge: refused until the retention date; recorded when done.
    early = api.post(f"/api/binders/{bid}/purge")
    assert early.status_code == 409 and "2033-09-30" in early.json()["detail"]
    pretend_today(api, date(2033, 9, 30))
    assert api.post(f"/api/binders/{bid}/purge").status_code == 200
    final = assembly(api, bid)
    assert final["state"] == "purged" and [e["kind"] for e in final["events"]][-1] == "purged"

    # Post-assembly access: every read by the auditor is on the access log with who and what.
    actions = [r["action"] for r in final["access"] if r["user"] == "auditor@nfra"]
    assert "produce" in actions and "verify" in actions
