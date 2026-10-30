"""Binders over the API against oak_binder_test: templates, creation, the clocks, the index
tree and the completeness view (spec 3A, 3F, 3G, 5.1)."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.conftest import unique

pytestmark = pytest.mark.db


def create_binder(api: TestClient, engagement: str | None = None, **extra: Any) -> dict[str, Any]:
    response = api.post(
        "/api/binders",
        json={"engagement": engagement or unique("ENG"), "template": "statutory", **extra},
    )
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


def test_templates_are_served(api: TestClient) -> None:
    response = api.get("/api/templates")
    assert response.status_code == 200
    names = [t["name"] for t in response.json()]
    assert names == ["statutory", "tax_audit", "bank_branch", "internal"]
    statutory = api.get("/api/templates/statutory").json()
    assert [s["code"] for s in statutory["sections"]][:3] == ["A", "B", "C"]
    assert {r["ref"] for r in statutory["required"]} == {"A-1", "B-1", "C-1", "W-1", "X-1", "Z-1"}
    assert api.get("/api/templates/group").status_code == 404


def test_new_binder_has_the_index_tree_and_every_required_paper_missing(api: TestClient) -> None:
    binder = create_binder(api)
    assert binder["state"] == "open"
    assert binder["template_label"] == "Statutory audit"
    assert binder["report_date"] is None and binder["days_to_assembly"] is None
    assert [s["code"] for s in binder["sections"]] == list("ABCDEFGHIJKLMNOPQRST") + [
        "W",
        "X",
        "Z",
    ]
    assert binder["missing_required"] == 6
    section_c = next(s for s in binder["sections"] if s["code"] == "C")
    assert section_c["name"] == "Materiality"
    assert section_c["papers"] == []
    assert [m["ref"] for m in section_c["missing"]] == ["C-1"]


def test_completeness_counts_only_required_references_with_no_paper(api: TestClient) -> None:
    binder = create_binder(api)
    api.post(
        f"/api/binders/{binder['id']}/papers",
        json={"ref": "C-1", "section": "C", "title": "Materiality memo"},
    ).raise_for_status()
    api.post(
        f"/api/binders/{binder['id']}/papers",
        json={"ref": "D-1", "section": "D", "title": "Cash lead"},
    ).raise_for_status()
    binder = api.get(f"/api/binders/{binder['id']}").json()
    assert binder["missing_required"] == 5
    section_c = next(s for s in binder["sections"] if s["code"] == "C")
    assert section_c["missing"] == []
    assert [p["ref"] for p in section_c["papers"]] == ["C-1"]
    section_d = next(s for s in binder["sections"] if s["code"] == "D")
    assert [p["ref"] for p in section_d["papers"]] == ["D-1"]


def test_a_required_paper_counts_only_in_its_own_section(api: TestClient) -> None:
    # Spec 3A: missing "per section". C-1 filed under section D does not satisfy C-1 in C.
    binder = create_binder(api)
    api.post(
        f"/api/binders/{binder['id']}/papers",
        json={"ref": "C-1", "section": "D", "title": "Misfiled materiality memo"},
    ).raise_for_status()
    binder = api.get(f"/api/binders/{binder['id']}").json()
    assert binder["missing_required"] == 6
    section_c = next(s for s in binder["sections"] if s["code"] == "C")
    assert [m["ref"] for m in section_c["missing"]] == ["C-1"]
    section_d = next(s for s in binder["sections"] if s["code"] == "D")
    assert [p["ref"] for p in section_d["papers"]] == ["C-1"]


def test_report_date_sets_both_clocks_and_the_countdown(api: TestClient) -> None:
    binder = create_binder(api, report_date="2026-09-30")
    assert binder["assembly_due"] == "2026-11-29"
    assert binder["retention_until"] == "2033-09-30"
    assert isinstance(binder["days_to_assembly"], int)


def test_leap_day_report_date_agrees_with_the_database_check(api: TestClient) -> None:
    # The database CHECK recomputes both clocks; a 29 February date proves the Python
    # arithmetic clamps exactly as PostgreSQL does.
    binder = create_binder(api, report_date="2028-02-29")
    assert binder["assembly_due"] == "2028-04-29"
    assert binder["retention_until"] == "2035-02-28"


def test_report_date_can_be_set_and_cleared_later(api: TestClient) -> None:
    binder = create_binder(api)
    dated = api.patch(f"/api/binders/{binder['id']}", json={"report_date": "2026-09-30"})
    assert dated.status_code == 200 and dated.json()["assembly_due"] == "2026-11-29"
    cleared = api.patch(f"/api/binders/{binder['id']}", json={"report_date": None})
    assert cleared.json()["report_date"] is None
    assert cleared.json()["assembly_due"] is None
    assert cleared.json()["retention_until"] is None


def test_an_empty_patch_changes_nothing(api: TestClient) -> None:
    # Regression: the handler used to apply report_date=None whenever the field was absent,
    # so an empty PATCH silently wiped the report date and both clocks.
    binder = create_binder(api, report_date="2026-09-30")
    untouched = api.patch(f"/api/binders/{binder['id']}", json={})
    assert untouched.status_code == 200
    assert untouched.json()["report_date"] == "2026-09-30"
    assert untouched.json()["assembly_due"] == "2026-11-29"
    assert untouched.json()["retention_until"] == "2033-09-30"
    unknown = api.patch(f"/api/binders/{binder['id']}", json={"engagement": "ENG-X"})
    assert unknown.status_code == 422  # unknown fields are refused, not ignored


def test_one_binder_per_engagement(api: TestClient) -> None:
    name = unique("ENG")
    create_binder(api, name)
    duplicate = api.post("/api/binders", json={"engagement": name, "template": "statutory"})
    assert duplicate.status_code == 409
    assert "already exists" in duplicate.json()["detail"]


def test_binder_validation(api: TestClient) -> None:
    blank = api.post("/api/binders", json={"engagement": "   ", "template": "statutory"})
    assert blank.status_code == 422
    unknown = api.post("/api/binders", json={"engagement": unique("ENG"), "template": "group"})
    assert unknown.status_code == 422  # request content, not a missing resource
    assert "No index template named 'group'" in unknown.json()["detail"]
    assert api.get("/api/binders/00000000-0000-0000-0000-000000000000").status_code == 404


def test_binders_are_listed(api: TestClient) -> None:
    # The test database may hold other binders (browser demos), so only the two created
    # here are asserted, in creation order.
    a = create_binder(api, unique("ENG-A"))
    b = create_binder(api, unique("ENG-B"), template="tax_audit")
    listed = api.get("/api/binders").json()
    mine = [(x["engagement"], x["template"]) for x in listed if x["id"] in {a["id"], b["id"]}]
    assert mine == [(a["engagement"], "statutory"), (b["engagement"], "tax_audit")]
