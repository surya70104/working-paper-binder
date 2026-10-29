"""Index templates (spec 3A, 3B): one per engagement type, the standard sections with the
spec's names, required papers with stable unique references, and an honest account of what
is still placeholder content. No database."""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from oak_binder.errors import NotFound
from oak_binder.models import SECTIONS, Template
from oak_binder.services.templates import (
    SPEC_SECTION_NAMES,
    TEMPLATES_DIR,
    TemplateError,
    list_templates,
    load_template,
    parse_template,
)

NAMES = [t.value for t in Template]


def raw(name: str = "statutory") -> dict[str, Any]:
    data: dict[str, Any] = json.loads((TEMPLATES_DIR / f"{name}.json").read_text(encoding="utf-8"))
    return copy.deepcopy(data)


# --- the four files as they stand ---------------------------------------------------------------


def test_one_template_per_engagement_type() -> None:
    assert [t.name for t in list_templates()] == NAMES
    assert NAMES == ["statutory", "tax_audit", "bank_branch", "internal"]


@pytest.mark.parametrize("name", NAMES)
def test_template_uses_the_standard_sections_with_the_spec_names(name: str) -> None:
    template = load_template(name)
    assert [s.code for s in template.sections] == list(SECTIONS)
    for code, spec_name in SPEC_SECTION_NAMES.items():
        assert template.section(code) is not None
        assert template.section(code).name == spec_name  # type: ignore[union-attr]


@pytest.mark.parametrize("name", NAMES)
def test_required_papers_are_unique_well_formed_and_in_known_sections(name: str) -> None:
    template = load_template(name)
    refs = [r.ref for r in template.required]
    assert refs and len(refs) == len(set(refs))
    codes = {s.code for s in template.sections}
    for r in template.required:
        assert r.section in codes
        assert r.ref.startswith(r.section + "-")  # project convention: <section>-<n>
        assert r.title.strip() and all(s.strip() for s in r.sa_refs)


@pytest.mark.parametrize("name", NAMES)
def test_every_template_is_draft_and_says_what_is_placeholder(name: str) -> None:
    template = load_template(name)
    assert template.draft
    findings = template.placeholders()
    assert any("generic names" in f and "D-T" in f for f in findings)
    assert any("no required paper in any financial statement area" in f for f in findings)
    assert any("chartered accountant" in f for f in findings)


def test_the_four_templates_do_not_yet_differ_by_engagement_type() -> None:
    # Documented placeholder: spec 3A asks for a template per engagement type, which only
    # means something once the required papers differ. Today they are the same six in every
    # file (only SA citations vary). This test records that fact; it is expected to be
    # replaced, not kept, when a chartered accountant supplies the real lists.
    lists = {
        name: tuple((r.ref, r.section, r.title) for r in load_template(name).required)
        for name in NAMES
    }
    assert len(set(lists.values())) == 1
    assert [r for r, _, _ in lists["statutory"]] == ["A-1", "B-1", "C-1", "W-1", "X-1", "Z-1"]


def test_unknown_template_is_not_found() -> None:
    with pytest.raises(NotFound, match="No index template named 'group'"):
        load_template("group")


# --- what the loader refuses (spec 3A, 3B) ----------------------------------------------------


def test_a_valid_file_parses() -> None:
    template = parse_template("statutory", raw())
    assert template.name == "statutory" and len(template.sections) == 23


def test_a_missing_standard_section_is_refused() -> None:
    data = raw()
    data["sections"] = [s for s in data["sections"] if s["code"] != "Z"]
    with pytest.raises(TemplateError, match=r"standard sections \['Z'\] are missing"):
        parse_template("statutory", data)


def test_a_non_standard_section_is_refused() -> None:
    data = raw()
    data["sections"].append({"code": "Y", "name": "Other"})
    with pytest.raises(TemplateError, match=r"sections \['Y'\] are not standard"):
        parse_template("statutory", data)


def test_a_repeated_section_is_refused() -> None:
    data = raw()
    data["sections"].append({"code": "A", "name": "Acceptance"})
    with pytest.raises(TemplateError, match="section code is repeated"):
        parse_template("statutory", data)


def test_renaming_a_spec_named_section_is_refused() -> None:
    data = raw()
    next(s for s in data["sections"] if s["code"] == "C")["name"] = "Thresholds"
    with pytest.raises(TemplateError, match="section C must be named 'Materiality'"):
        parse_template("statutory", data)


def test_a_repeated_required_reference_is_refused() -> None:
    data = raw()
    data["required"].append(dict(data["required"][0]))
    with pytest.raises(TemplateError, match=r"references \['A-1'\] are repeated"):
        parse_template("statutory", data)


@pytest.mark.parametrize("field", ["ref", "section", "title"])
def test_a_blank_required_field_is_refused(field: str) -> None:
    data = raw()
    data["required"][0][field] = "  "
    with pytest.raises(TemplateError, match=f"{field!r} must be non-blank text"):
        parse_template("statutory", data)


def test_a_required_paper_in_an_absent_section_is_refused() -> None:
    data = raw()
    data["required"][0]["section"] = "Q"
    data["sections"] = [s for s in data["sections"] if s["code"] != "Q"]
    with pytest.raises(TemplateError, match="standard sections \\['Q'\\] are missing"):
        parse_template("statutory", data)
    data = raw()
    data["required"][0]["section"] = "V"  # V is not a standard section at all
    with pytest.raises(TemplateError, match="section 'V' is not in this template"):
        parse_template("statutory", data)


def test_sa_refs_must_be_a_list_of_text() -> None:
    data = raw()
    data["required"][0]["sa_refs"] = "SA 210"
    with pytest.raises(TemplateError, match="sa_refs must be a list of text"):
        parse_template("statutory", data)
    data["required"][0]["sa_refs"] = ["SA 210", ""]
    with pytest.raises(TemplateError, match="sa_refs must be a list of text"):
        parse_template("statutory", data)


def test_unknown_or_missing_keys_are_refused() -> None:
    data = raw()
    data["required"][0]["sa_ref"] = data["required"][0].pop(
        "sa_refs"
    )  # a typo would drop citations
    with pytest.raises(
        TemplateError, match=r"unknown keys \['sa_ref'\], missing keys \['sa_refs'\]"
    ):
        parse_template("statutory", data)
    data = raw()
    data["notes"] = "x"
    with pytest.raises(TemplateError, match=r"unknown keys \['notes'\]"):
        parse_template("statutory", data)


def test_the_file_must_declare_its_own_name() -> None:
    with pytest.raises(TemplateError, match="file declares name 'statutory'"):
        parse_template("tax_audit", raw("statutory"))
