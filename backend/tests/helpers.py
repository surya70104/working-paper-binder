"""Builders shared by the API tests: a binder, a paper, the sign-off chain, a complete
assemblable file."""

from __future__ import annotations

import copy
import json
import uuid
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import PREPARER, REVIEWER, act_as, unique

PARTNER = "partner@firm"

PAPER: dict[str, Any] = {
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

# The test database is shared with browser demos and preserved (README "Test database and
# browser-demo data"), and identical bytes are one document across binders (D17), so the
# evidence bytes carry a per-session trailer: no demo row can be the document a test expects
# to create. Module run ids get the same treatment (generated_fixture): one paper per run holds
# across every binder (D31).
SESSION = uuid.uuid4().hex[:12]
PDF = (
    b"%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\ntrailer << /Root 1 0 R >>\n%%EOF\n"
    + f"%% test session {SESSION}\n".encode()
)
CSV = (
    b"invoice,date,amount\nINV-001,2026-03-31,100000\nINV-002,2026-03-30,250000\n"
    + f"# test session {SESSION}\n".encode()
)


def create_binder(api: TestClient, **extra: Any) -> dict[str, Any]:
    response = api.post(
        "/api/binders", json={"engagement": unique("ENG"), "template": "statutory", **extra}
    )
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


def create_paper(api: TestClient, binder_id: str, **overrides: Any) -> dict[str, Any]:
    response = api.post(f"/api/binders/{binder_id}/papers", json={**PAPER, **overrides})
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


def upload(
    api: TestClient,
    paper_id: str,
    name: str,
    data: bytes,
    *,
    identifying_chars: str | None = None,
    amendment_reason: str | None = None,
    expected: int = 201,
) -> dict[str, Any]:
    form = {
        k: v
        for k, v in {
            "identifying_chars": identifying_chars,
            "amendment_reason": amendment_reason,
        }.items()
        if v is not None
    }
    response = api.post(
        f"/api/papers/{paper_id}/attachments",
        files={"file": (name, data, "application/octet-stream")},
        data=form,
    )
    assert response.status_code == expected, f"upload: {response.status_code} {response.text}"
    result: dict[str, Any] = response.json()
    return result


def complete_binder(api: TestClient, report_date: str = "2026-09-30") -> dict[str, Any]:
    """A dated statutory binder with every required paper created and signed off, so that
    nothing blocks assembly. The C-1 paper carries one CSV attachment."""
    binder = create_binder(api, report_date=report_date)
    template = api.get("/api/templates/statutory").json()
    for required in template["required"]:
        paper = create_paper(
            api,
            binder["id"],
            ref=required["ref"],
            section=required["section"],
            title=required["title"],
            sa_refs=required["sa_refs"],
        )
        if required["ref"] == "C-1":
            upload(api, paper["id"], "benchmark.csv", CSV, identifying_chars="FY26 TB rows 1-2")
        full_chain(api, paper["id"])
    result: dict[str, Any] = api.get(f"/api/binders/{binder['id']}").json()
    return result


FIXTURES = Path(__file__).parent / "fixtures" / "generated"


def generated_fixture(source: str) -> dict[str, Any]:
    """A module delivery from tests/fixtures/generated, its run id made unique to this call:
    one paper per run holds across every binder in the shared test database (D31), so the
    fixture's own id may already be filed by a demo. The WorkMind double recognises the
    fixture's run id as a prefix."""
    data: dict[str, Any] = json.loads((FIXTURES / f"{source}.json").read_text(encoding="utf-8"))
    data = copy.deepcopy(data)
    run_id = data["generated"].get("run_id")
    if run_id:
        data["generated"]["run_id"] = f"{run_id}-{uuid.uuid4().hex[:8]}"
    return data
