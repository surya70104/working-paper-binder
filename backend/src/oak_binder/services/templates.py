"""Index templates per engagement type (spec 3A), loaded from the JSON files in
``oak_binder/templates`` and validated once on first use.

What the specification fixes, and the loader enforces:
- one template per engagement type: statutory, tax audit, bank branch, internal;
- the standard sections A, B, C, D-T, W, X, Z, all present, with the spec's names for the
  six it names (acceptance, planning and risk, materiality, completion, report and opinion,
  EQR);
- required papers with a stable, unique, non-blank reference, a section the template has, a
  title, and SA references (spec 3B).

What the specification leaves to the firm, and the loader only reports (``placeholders``):
the names of the financial statement areas D-T, which papers each engagement type
requires, and the SA references those papers carry. Until a chartered accountant supplies
those, every file is marked draft. See docs/TEMPLATE_AUTHORING.md.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

from oak_binder.errors import NotFound
from oak_binder.models.enums import SECTIONS, Template

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

# Spec 3A names these sections; D-T are "financial statement areas" without names.
SPEC_SECTION_NAMES: dict[str, str] = {
    "A": "Acceptance",
    "B": "Planning and risk",
    "C": "Materiality",
    "W": "Completion",
    "X": "Report and opinion",
    "Z": "EQR",
}
AREA_SECTIONS: tuple[str, ...] = tuple(c for c in SECTIONS if c not in SPEC_SECTION_NAMES)
GENERIC_AREA_PREFIX = "Financial statement area"

TEMPLATE_KEYS = {"name", "label", "status", "sections", "required"}
# Optional (Stage E, D32): the firm's map of Schedule III heads to areas D-T, and approved
# wording for the lead schedules the Spine produces. Shipped files carry an empty map.
TEMPLATE_OPTIONAL_KEYS = {"areas"}
SECTION_KEYS = {"code", "name"}
REQUIRED_KEYS = {"ref", "section", "title", "sa_refs"}
AREA_KEYS = {"heads"}
# References the Binder itself generates (Stage E, D32): one lead schedule per area, in that
# area's section, and the adjustment chain in W. A template may require them, so that the
# generated paper fills the slot, but only in the section where they are generated.
ADJUSTMENT_CHAIN_REF = "W-ADJ"
ADJUSTMENT_CHAIN_SECTION = "W"
LEAD_SCHEDULE_SUFFIX = "-L"
AREA_OPTIONAL_KEYS = {"objective", "procedure"}


def generated_section(ref: str) -> str | None:
    """The section in which the Binder generates a paper with this reference (D32): ``<area>-L``
    in its area D-T, ``W-ADJ`` in W; None for every other reference."""
    if ref == ADJUSTMENT_CHAIN_REF:
        return ADJUSTMENT_CHAIN_SECTION
    area = ref[: -len(LEAD_SCHEDULE_SUFFIX)]
    if ref.endswith(LEAD_SCHEDULE_SUFFIX) and area in AREA_SECTIONS:
        return area
    return None


class TemplateError(ValueError):
    """A template file does not satisfy spec 3A or 3B."""


@dataclass(frozen=True)
class Section:
    code: str
    name: str


@dataclass(frozen=True)
class RequiredPaper:
    ref: str
    section: str
    title: str
    sa_refs: tuple[str, ...]


@dataclass(frozen=True)
class AreaMap:
    """What the firm says an area covers: Schedule III head ids, spelled as the Spine's tree
    spells them (a listed head covers its descendants; see services.area_map), and the
    approved wording, if any, for a Spine-produced lead schedule's objective and procedure.
    Nothing here is invented by the Binder."""

    heads: tuple[str, ...]
    objective: str | None = None
    procedure: str | None = None


@dataclass(frozen=True)
class IndexTemplate:
    name: str
    label: str
    status: str
    sections: tuple[Section, ...]
    required: tuple[RequiredPaper, ...]
    areas: Mapping[str, AreaMap] = field(default_factory=dict)

    def section(self, code: str) -> Section | None:
        return next((s for s in self.sections if s.code == code), None)

    def generated_required(self) -> list[RequiredPaper]:
        """Required papers the Binder generates itself (lead schedules, the adjustment chain)."""
        return [r for r in self.required if generated_section(r.ref) is not None]

    @property
    def draft(self) -> bool:
        return self.status.lower().startswith("draft")

    def placeholders(self) -> list[str]:
        """Content the specification leaves to the firm and this file has not yet supplied."""
        findings: list[str] = []
        unnamed = [s.code for s in self.sections if s.name.startswith(GENERIC_AREA_PREFIX)]
        if unnamed:
            findings.append(
                f"financial statement areas {unnamed[0]}-{unnamed[-1]} ({len(unnamed)}) carry "
                "generic names; the firm's area names are not set"
            )
        if not any(r.section in AREA_SECTIONS for r in self.required):
            findings.append(
                "no required paper in any financial statement area D-T; lead schedules per "
                "area are not defined"
            )
        without_refs = [r.ref for r in self.required if not r.sa_refs]
        if without_refs:
            findings.append(
                f"no SA references on required papers {', '.join(without_refs)}; the "
                "chartered accountant's mapping is not set"
            )
        if not self.areas:
            findings.append(
                "no area map (areas): lead schedules use a default map derived from the Spine's "
                "tree (D38) until the firm's map is entered (TEMPLATE_AUTHORING item 1)"
            )
        else:
            unmapped = [c for c in AREA_SECTIONS if c not in self.areas]
            if unmapped:
                findings.append(
                    f"areas {', '.join(unmapped)} have no Schedule III heads in the area map; "
                    "no lead schedule can be generated for them"
                )
        if self.draft:
            findings.append("marked draft: not yet reviewed by a chartered accountant")
        return findings


def template_names() -> list[str]:
    return [t.value for t in Template]


def _text(raw: Mapping[str, Any], key: str, where: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise TemplateError(f"{where}: {key!r} must be non-blank text")
    return value.strip()


def _keys(
    raw: Mapping[str, Any], allowed: set[str], where: str, optional: set[str] | None = None
) -> None:
    unknown = sorted(set(raw) - allowed - (optional or set()))
    missing = sorted(allowed - set(raw))
    if unknown or missing:
        raise TemplateError(f"{where}: unknown keys {unknown}, missing keys {missing}")


def _optional_text(raw: Mapping[str, Any], key: str, where: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise TemplateError(f"{where}: {key!r} must be non-blank text or absent")
    return value.strip()


def parse_areas(raw: Any, codes: list[str], where: str) -> dict[str, AreaMap]:
    """Step 1 of the area-map check (D32): syntax only. Keys are area sections D-T of this
    template; each lists non-blank head ids, none listed twice anywhere; approved wording is
    optional text. Whether the ids are real heads, and whether areas overlap once expanded,
    is checked against the Spine's tree by services.area_map."""
    if not isinstance(raw, dict):
        raise TemplateError(f"{where}: 'areas' must be an object keyed by area section codes")
    areas: dict[str, AreaMap] = {}
    seen: dict[str, str] = {}
    for code, entry in raw.items():
        if code not in codes or code not in AREA_SECTIONS:
            raise TemplateError(
                f"{where} areas: {code!r} is not a financial statement area D-T of this template"
            )
        if not isinstance(entry, dict):
            raise TemplateError(f"{where} area {code}: must be an object with 'heads'")
        _keys(entry, AREA_KEYS, f"{where} area {code}", AREA_OPTIONAL_KEYS)
        heads = entry["heads"]
        if not isinstance(heads, list) or not all(isinstance(h, str) and h.strip() for h in heads):
            raise TemplateError(
                f"{where} area {code}: 'heads' must be a list of non-blank head ids"
            )
        cleaned = tuple(h.strip() for h in heads)
        for head in cleaned:
            if head in seen:
                raise TemplateError(
                    f"{where} areas: head {head!r} is listed under {seen[head]} and {code}; a "
                    "head is listed once"
                )
            seen[head] = code
        areas[code] = AreaMap(
            cleaned,
            _optional_text(entry, "objective", f"{where} area {code}"),
            _optional_text(entry, "procedure", f"{where} area {code}"),
        )
    return areas


def parse_template(name: str, raw: Mapping[str, Any]) -> IndexTemplate:
    """Validate one template document against spec 3A and 3B."""
    where = f"template {name}"
    _keys(raw, TEMPLATE_KEYS, where, TEMPLATE_OPTIONAL_KEYS)
    if raw["name"] != name:
        raise TemplateError(f"{where}: file declares name {raw['name']!r}")
    label = _text(raw, "label", where)
    status = _text(raw, "status", where)

    if not isinstance(raw["sections"], list) or not raw["sections"]:
        raise TemplateError(f"{where}: 'sections' must be a non-empty list")
    sections: list[Section] = []
    for entry in raw["sections"]:
        _keys(entry, SECTION_KEYS, f"{where} section")
        code = _text(entry, "code", f"{where} section")
        sections.append(Section(code, _text(entry, "name", f"{where} section {code}")))
    codes = [s.code for s in sections]
    if len(codes) != len(set(codes)):
        raise TemplateError(f"{where}: a section code is repeated")
    unknown = sorted(set(codes) - set(SECTIONS))
    if unknown:
        raise TemplateError(f"{where}: sections {unknown} are not standard sections (spec 3A)")
    absent = [c for c in SECTIONS if c not in codes]
    if absent:
        raise TemplateError(f"{where}: standard sections {absent} are missing (spec 3A)")
    for code, spec_name in SPEC_SECTION_NAMES.items():
        actual = next(s.name for s in sections if s.code == code)
        if actual != spec_name:
            raise TemplateError(
                f"{where}: section {code} must be named {spec_name!r} (spec 3A), not {actual!r}"
            )

    if not isinstance(raw["required"], list):
        raise TemplateError(f"{where}: 'required' must be a list")
    required: list[RequiredPaper] = []
    for entry in raw["required"]:
        _keys(entry, REQUIRED_KEYS, f"{where} required paper")
        ref = _text(entry, "ref", f"{where} required paper")
        section = _text(entry, "section", f"{where} required paper {ref}")
        title = _text(entry, "title", f"{where} required paper {ref}")
        sa_refs = entry["sa_refs"]
        if not isinstance(sa_refs, list) or not all(
            isinstance(s, str) and s.strip() for s in sa_refs
        ):
            raise TemplateError(f"{where} required paper {ref}: sa_refs must be a list of text")
        if section not in codes:
            raise TemplateError(
                f"{where} required paper {ref}: section {section!r} is not in this template"
            )
        required.append(RequiredPaper(ref, section, title, tuple(s.strip() for s in sa_refs)))
    refs = [r.ref for r in required]
    if len(refs) != len(set(refs)):
        repeated = sorted({r for r in refs if refs.count(r) > 1})
        raise TemplateError(f"{where}: required references {repeated} are repeated (spec 3B)")
    for paper in required:
        generated_in = generated_section(paper.ref)
        if generated_in is not None and paper.section != generated_in:
            raise TemplateError(
                f"{where} required paper {paper.ref}: the Binder generates {paper.ref} in section "
                f"{generated_in} (D32), so it cannot be required in section {paper.section}; a "
                "paper there would never satisfy the requirement"
            )

    areas = parse_areas(raw["areas"], codes, where) if "areas" in raw else {}
    return IndexTemplate(name, label, status, tuple(sections), tuple(required), areas)


@cache
def load_template(name: str) -> IndexTemplate:
    if name not in template_names():
        raise NotFound(f"No index template named {name!r}; choose one of {template_names()}")
    raw = json.loads((TEMPLATES_DIR / f"{name}.json").read_text(encoding="utf-8"))
    return parse_template(name, raw)


def list_templates() -> list[IndexTemplate]:
    return [load_template(name) for name in template_names()]
