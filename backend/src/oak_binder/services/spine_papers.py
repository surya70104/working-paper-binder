"""Papers the Financial Spine produces (spec 3A "lead schedule per area, tying to the
Financial Spine", 3C "every lead schedule, and the adjustment chain"; Pass 2 Stage E, D32).

Step E3 adds the adjustment chain: one paper per binder, ``W-ADJ`` in section W Completion
(decision 3), carrying every adjustment of the version in all three statuses and the
uncorrected schedule exactly as served, with a reference to each working paper an
adjustment names by exact string match and a listing of the names that match no paper
(decision 7; information, never a blocker).

Step E2: the lead schedules. A person asks for them on the Binder screen; the Binder reads the
binder's linked, **locked** Spine version (decision 1), works out which heads each area covers
from the template's area map and the Spine's tree (`services.area_map`: descent by the served
``parent`` field only), and files one draft paper per mapped area through the Stage D intake
with ``source = "spine"``. Everything in the paper is what the Spine served: lines, ledgers,
the Spine's own per-head totals and the adjustments touching the area. The Binder adds nothing
up, rounds nothing and nets nothing (CAF D30); where the Spine served no ledger or no figure,
the paper says so in those words and never writes a zero or "nil" it was not given (decision
13). ``objective`` and ``procedure`` arrive empty, or with the template's approved wording,
and stay a person's to write (decision 5). One FS-line reference is written per presentation
line of the area, so the cross-reference map draws the paper as the line's lead schedule.

The run id is ``<binder_id>/<version_id>/<version_hash>/<area>`` (decision 14): unique per
binder, unchanged while the Spine is unchanged, so a repeated request is refused as "one paper
per run" naming the existing paper.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from oak_binder.errors import BinderError, Conflict, Invalid, NotFound, SpineUnavailable
from oak_binder.models import Binder, BinderState, Wp, WpGeneration
from oak_binder.schemas.generated import (
    FreshnessOut,
    Generated,
    GeneratedPaperIn,
    PaperFields,
    SpineAdjustment,
    SpineAdjustmentLine,
    SpineBlock,
    SpineFsLine,
    SpineHeadTotal,
    SpineLedgerRow,
)
from oak_binder.services import area_map, fs_lines
from oak_binder.services import generated as generated_service
from oak_binder.services import papers as paper_service
from oak_binder.services import xrefs as xref_service
from oak_binder.services.area_map import AreaMapCheck, ResolvedAreas
from oak_binder.services.spine_client import SpineClient, SpineTree, SpineVersion
from oak_binder.services.templates import AREA_SECTIONS, AreaMap, IndexTemplate, load_template

MODULE = "oak_spine"
NO_FIGURE = "no figure served"
CHAIN_REF = "W-ADJ"
CHAIN_SECTION = "W"  # Completion (spec 3A): the chain is a completion record (decision 3)
# Every reference the Binder writes from a Spine paper is created by the Spine, not by the
# person who asked (who is the provenance row's received_by). The marker is how a Binder-
# written reference is told apart from one a person typed (step E4, ownership rule).
REFERENCE_CREATOR = MODULE


NO_AREAS = (
    "no area map for template {template} and the Spine's tree has no heads to derive one from, so "
    "no lead schedule can be generated (TEMPLATE_AUTHORING item 1; D38)"
)


def _require_area(resolved: ResolvedAreas, template: IndexTemplate, code: str) -> None:
    if not resolved.areas:
        raise Invalid(NO_AREAS.format(template=template.name))
    if code not in resolved.areas:
        where = (
            f"the area map of template {template.name}"
            if resolved.source == "template"
            else "the map derived from the Spine's tree (the template has none; D38)"
        )
        raise Invalid(
            f"area {code} has no Schedule III heads in {where}; no lead schedule can be generated "
            "for it"
        )


def lead_schedule_ref(area: str) -> str:
    return f"{area}-L"


# --- readiness ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Readiness:
    """Whether Spine papers can be generated for this binder now, and if not, why, with the
    error class the Binder's conventions give that refusal: ``Conflict`` (409) for a state the
    binder is in (not open, not linked, version unlocked), ``SpineUnavailable`` (503) for no
    Spine or one that cannot answer, ``NotFound`` (404) for a version the Spine no longer has."""

    ok: bool
    reason: str | None
    version: SpineVersion | None = None
    error: type[BinderError] = Conflict

    def refuse(self, what: str) -> BinderError:
        return self.error(f"{what}: {self.reason}")


@dataclass(frozen=True)
class CurrentVersion:
    """The Spine's current answer for the binder's linked version, or why there is none."""

    version: SpineVersion | None
    problem: str | None
    error: type[BinderError] = Conflict


def current_version(client: SpineClient | None, binder: Binder) -> CurrentVersion:
    if binder.spine_version_id is None:
        return CurrentVersion(
            None, "the binder is not linked to a Financial Spine version (D29)", Conflict
        )
    if client is None:
        return CurrentVersion(
            None, "no Financial Spine is configured (OAK_SPINE_URL)", SpineUnavailable
        )
    try:
        return CurrentVersion(client.version(binder.spine_version_id), None)
    except SpineUnavailable as exc:
        return CurrentVersion(None, str(exc), SpineUnavailable)
    except NotFound as exc:
        return CurrentVersion(None, str(exc), NotFound)


def readiness(client: SpineClient | None, binder: Binder) -> Readiness:
    if binder.state != BinderState.OPEN:
        return Readiness(
            False,
            f"the binder is {binder.state}: Spine papers are generated while it is open",
            error=Conflict,
        )
    current = current_version(client, binder)
    if current.version is None:
        return Readiness(False, current.problem, error=current.error)
    version = current.version
    if not version.is_locked or not version.hash:
        return Readiness(
            False,
            f"Spine version {version.label!r} is not locked: Spine papers are generated from a "
            "locked version only, so their figures carry the version's hash (Stage E decision 1)",
            error=Conflict,
        )
    return Readiness(True, None, version)


# --- status -------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Freshness:
    """Whether a Spine paper still matches the binder's linked version (step E4)."""

    state: str  # "current" | "stale" | "not_checked"
    detail: str | None
    recorded_version_id: uuid.UUID | None
    recorded_version_label: str | None


def freshness(
    block: dict[str, Any], binder: Binder, version: SpineVersion | None, problem: str | None
) -> Freshness:
    """Compare the version a Spine paper records with the binder's link and the Spine's current
    answer. Ids and hashes only; no figure is re-read."""
    recorded_id = _uuid_or_none(block.get("version_id"))
    recorded_label = (
        block.get("version_label") if isinstance(block.get("version_label"), str) else None
    )
    recorded_hash = (
        block.get("version_hash") if isinstance(block.get("version_hash"), str) else None
    )
    if binder.spine_version_id is None:
        return Freshness(
            "stale",
            f"built from Spine version {recorded_label!r} ({recorded_id}); the binder is no "
            "longer linked",
            recorded_id,
            recorded_label,
        )
    if recorded_id != binder.spine_version_id:
        now_label = version.label if version is not None else str(binder.spine_version_id)
        return Freshness(
            "stale",
            f"built from Spine version {recorded_label!r} ({recorded_id}); the binder is now "
            f"linked to {now_label!r} ({binder.spine_version_id})",
            recorded_id,
            recorded_label,
        )
    if version is None:
        return Freshness(
            "not_checked", f"freshness not checked: {problem}", recorded_id, recorded_label
        )
    if version.hash != recorded_hash:
        return Freshness(
            "stale",
            f"built from Spine version {recorded_label!r} with hash {recorded_hash}; the "
            f"version's hash is now {version.hash}",
            recorded_id,
            recorded_label,
        )
    return Freshness("current", None, recorded_id, recorded_label)


def _uuid_or_none(value: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value)) if value else None
    except ValueError:
        return None


@dataclass(frozen=True)
class AreaStatus:
    code: str
    name: str
    mapped: bool
    listed_heads: tuple[str, ...]
    paper_id: uuid.UUID | None
    ref: str
    state: str  # "none" | "current" | "stale" | "not_checked"
    detail: str | None = None
    recorded_version_id: uuid.UUID | None = None
    recorded_version_label: str | None = None


@dataclass(frozen=True)
class ChainStatus:
    """The adjustment-chain paper (E3): needs a linked, locked version, no area map."""

    ref: str
    section: str
    paper_id: uuid.UUID | None
    state: str  # "none" | "current" | "stale" | "not_checked"
    can_generate: bool
    reason: str | None
    detail: str | None = None
    recorded_version_id: uuid.UUID | None = None
    recorded_version_label: str | None = None


@dataclass(frozen=True)
class SpinePapersStatus:
    can_generate: bool
    reason: str | None
    version_id: uuid.UUID | None
    version_label: str | None
    version_hash: str | None
    areas: tuple[AreaStatus, ...]
    chain: ChainStatus
    map_problems: tuple[str, ...] = field(default_factory=tuple)
    unassigned_heads: tuple[str, ...] = field(default_factory=tuple)
    # D38: "template" (the template's own map), "derived" (from the Spine's tree) or "none".
    map_source: str = "none"
    beyond_letters: tuple[str, ...] = field(default_factory=tuple)


def _spine_rows(session: Session, binder: Binder) -> list[tuple[Wp, WpGeneration, dict[str, Any]]]:
    rows = session.execute(
        select(Wp, WpGeneration)
        .join(WpGeneration, WpGeneration.wp_id == Wp.id)
        .where(Wp.binder_id == binder.id, WpGeneration.source == "spine")
        .order_by(WpGeneration.received_at, WpGeneration.id)
    ).all()
    out: list[tuple[Wp, WpGeneration, dict[str, Any]]] = []
    for paper, generation in rows:
        block = generation.payload.get("spine") if isinstance(generation.payload, dict) else None
        if isinstance(block, dict):
            out.append((paper, generation, block))
    return out


def _lead_schedules(session: Session, binder: Binder) -> dict[str, tuple[Wp, WpGeneration]]:
    """Area code → the paper and its latest generation row, for Spine lead schedules of this
    binder."""
    found: dict[str, tuple[Wp, WpGeneration]] = {}
    for paper, generation, block in _spine_rows(session, binder):
        if block.get("kind") == "lead_schedule" and block.get("area"):
            found[str(block["area"])] = (paper, generation)  # latest row wins
    return found


def _block_of(generation: WpGeneration) -> dict[str, Any]:
    block = generation.payload.get("spine") if isinstance(generation.payload, dict) else None
    return block if isinstance(block, dict) else {}


def stale_notes(session: Session, client: SpineClient | None, binder: Binder) -> list[str]:
    """One line per Spine paper that is stale or whose freshness cannot be checked, for the
    assembly status's not-checked list (decision 8: information, never a blocker)."""
    rows = _spine_rows(session, binder)
    if not rows:
        return []
    current = current_version(client, binder)
    version, problem = current.version, current.problem
    notes: list[str] = []
    latest: dict[uuid.UUID, tuple[Wp, dict[str, Any]]] = {}
    for paper, _generation, block in rows:
        latest[paper.id] = (paper, block)  # the latest row per paper wins
    for paper, block in latest.values():
        fresh = freshness(block, binder, version, problem)
        if fresh.state != "current":
            notes.append(
                f"Spine paper {paper.ref}: {fresh.detail} (information; regenerate while the "
                "binder is open)"
            )
    return notes


def paper_freshness(
    client: SpineClient | None, binder: Binder, generation: WpGeneration | None
) -> FreshnessOut | None:
    """The freshness of one paper's latest generation row, for the paper screen; None for a
    hand-made paper or one another module produced (step E5)."""
    if generation is None or generation.source != "spine":
        return None
    current = current_version(client, binder)
    fresh = freshness(_block_of(generation), binder, current.version, current.problem)
    return FreshnessOut(
        state=fresh.state,  # a Freshness state is one of the three literals
        detail=fresh.detail,
        recorded_version_id=fresh.recorded_version_id,
        recorded_version_label=fresh.recorded_version_label,
    )


def _chain(session: Session, binder: Binder) -> tuple[Wp, WpGeneration] | None:
    """The binder's adjustment-chain paper and its latest generation row, if any."""
    found: tuple[Wp, WpGeneration] | None = None
    for paper, generation, block in _spine_rows(session, binder):
        if block.get("kind") == "adjustment_chain":
            found = (paper, generation)  # latest row wins
    return found


def status(session: Session, client: SpineClient | None, binder: Binder) -> SpinePapersStatus:
    template = load_template(binder.template)
    ready = readiness(client, binder)
    linked = current_version(client, binder)
    linked_version, link_problem = linked.version, linked.problem
    existing = _lead_schedules(session, binder)
    problems: tuple[str, ...] = ()
    unassigned: tuple[str, ...] = ()
    reason = ready.reason
    resolved = area_map.from_template(template)
    if ready.ok and client is not None:
        try:
            tree = client.tree()
        except SpineUnavailable as exc:
            reason = str(exc)
        else:
            resolved = area_map.resolve(template, tree)
            if not resolved.areas:
                reason = NO_AREAS.format(template=template.name)
            else:
                checked = area_map.check_areas(resolved.areas, tree)
                problems = checked.problems
                unassigned = checked.unassigned
                if problems:
                    reason = "the area map is refused against the Spine's tree: " + "; ".join(
                        problems
                    )
    areas: list[AreaStatus] = []
    for code in AREA_SECTIONS:
        section = template.section(code)
        name = resolved.names.get(code) or (section.name if section else f"Section {code}")
        area = resolved.areas.get(code)
        paper_generation = existing.get(code)
        if paper_generation is not None:
            paper, generation = paper_generation
            fresh = freshness(_block_of(generation), binder, linked_version, link_problem)
            areas.append(
                AreaStatus(
                    code,
                    name,
                    area is not None,
                    area.heads if area else (),
                    paper.id,
                    paper.ref,
                    fresh.state,
                    fresh.detail,
                    fresh.recorded_version_id,
                    fresh.recorded_version_label,
                )
            )
        else:
            detail = None if area is not None else "no Schedule III heads in the area map"
            areas.append(
                AreaStatus(
                    code,
                    name,
                    area is not None,
                    area.heads if area else (),
                    None,
                    lead_schedule_ref(code),
                    "none",
                    detail,
                )
            )
    version = ready.version
    chain = _chain(session, binder)
    chain_fresh = (
        freshness(_block_of(chain[1]), binder, linked_version, link_problem) if chain else None
    )
    return SpinePapersStatus(
        can_generate=ready.ok and reason is None,
        reason=reason,
        map_source=resolved.source,
        beyond_letters=resolved.beyond_letters,
        version_id=version.version_id if version else None,
        version_label=version.label if version else None,
        version_hash=version.hash if version else None,
        areas=tuple(areas),
        chain=ChainStatus(
            CHAIN_REF,
            CHAIN_SECTION,
            chain[0].id if chain else None,
            chain_fresh.state if chain_fresh else "none",
            ready.ok and chain is None,
            ready.reason
            if not ready.ok
            else ("the adjustment chain already exists" if chain else None),
            chain_fresh.detail if chain_fresh else None,
            chain_fresh.recorded_version_id if chain_fresh else None,
            chain_fresh.recorded_version_label if chain_fresh else None,
        ),
        map_problems=problems,
        unassigned_heads=unassigned,
    )


# --- building a lead schedule -------------------------------------------------------------------


def _str_or_none(value: Any, what: str) -> str | None:
    """A figure exactly as served: a string, or None for no figure. Anything else is an
    answer the Binder does not understand, never one it converts."""
    if value is None or isinstance(value, str):
        return value
    raise SpineUnavailable(f"the Spine served {what} as {type(value).__name__}, not text")


def served(value: str | None) -> str:
    return value if value is not None else NO_FIGURE


def _cell(text: str | None) -> str:
    return (text or "").replace("|", "\\|").replace("\n", " ")


def _row(*cells: str) -> str:
    return "| " + " | ".join(cells) + " |"


def _text_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _adjustment_from(raw: dict[str, Any], raw_lines: list[dict[str, Any]]) -> SpineAdjustment:
    """An adjustment exactly as served: kind, status (proposed, accepted or refused, all
    kept), narration, the working paper and finding it names, who proposed and decided it,
    and its lines with debit and credit as the Spine's strings."""
    adj_id = str(raw.get("adjustment_id") or "")
    return SpineAdjustment(
        adjustment_id=adj_id,
        kind=str(raw.get("kind") or ""),
        status=str(raw.get("status") or ""),
        narration=_text_or_none(raw.get("narration")),
        working_paper_ref=_text_or_none(raw.get("working_paper_ref")),
        finding_ref=_text_or_none(raw.get("finding_ref")),
        proposed_by=_text_or_none(raw.get("proposed_by")),
        proposed_at=_text_or_none(raw.get("proposed_at")),
        decided_by=_text_or_none(raw.get("decided_by")),
        decided_at=_text_or_none(raw.get("decided_at")),
        decision_note=_text_or_none(raw.get("decision_note")),
        lines=[
            SpineAdjustmentLine(
                line_no=ln.get("line_no") if isinstance(ln.get("line_no"), int) else None,
                ledger_key=_text_or_none(ln.get("ledger_key")),
                ledger_name=_text_or_none(ln.get("ledger_name")),
                head_id=_text_or_none(ln.get("head_id")),
                dr=_str_or_none(ln.get("dr"), f"adjustment {adj_id} dr"),
                cr=_str_or_none(ln.get("cr"), f"adjustment {adj_id} cr"),
            )
            for ln in raw_lines
        ],
    )


def _block_for_area(
    client: SpineClient,
    version: SpineVersion,
    tree: SpineTree,
    area: AreaMap,
    checked: AreaMapCheck,
    code: str,
) -> SpineBlock:
    covered = checked.coverage[code]
    heads = area_map.heads_of(area, tree)
    presentation = client.presentation(version.version_id)
    lines = [
        SpineFsLine(
            head_id=line.head_id,
            label=line.label,
            current=_str_or_none(line.current, f"line {line.head_id}"),
            prior=_str_or_none(line.prior, f"line {line.head_id}"),
        )
        for line in presentation.lines
        if line.head_id in covered
    ]
    balances = client.balances(version.version_id)
    ledgers: list[SpineLedgerRow] = []
    for raw in balances.get("ledgers") or []:
        if not isinstance(raw, dict) or raw.get("head_id") not in covered:
            continue
        key = str(raw.get("ledger_key") or "")
        ledgers.append(
            SpineLedgerRow(
                head_id=str(raw["head_id"]),
                ledger_key=key,
                ledger_name=str(raw.get("ledger_name") or key),
                parent_chain=[str(p) for p in (raw.get("parent_chain") or [])],
                unadjusted=_str_or_none(raw.get("unadjusted"), f"ledger {key} unadjusted"),
                reclass=_str_or_none(raw.get("reclass"), f"ledger {key} reclass"),
                corrections=_str_or_none(raw.get("corrections"), f"ledger {key} corrections"),
                adjusted=_str_or_none(raw.get("adjusted"), f"ledger {key} adjusted"),
                prior_closing=_str_or_none(raw.get("prior_closing"), f"ledger {key} prior"),
            )
        )
    totals: list[SpineHeadTotal] = []
    for raw in balances.get("groups") or []:
        if not isinstance(raw, dict) or raw.get("head_id") not in covered:
            continue
        head_id = str(raw["head_id"])
        totals.append(
            SpineHeadTotal(
                head_id=head_id,
                ledgers=int(raw.get("ledgers") or 0),
                unadjusted=_str_or_none(raw.get("unadjusted"), f"head {head_id} unadjusted"),
                adjusted=_str_or_none(raw.get("adjusted"), f"head {head_id} adjusted"),
                prior_closing=_str_or_none(raw.get("prior_closing"), f"head {head_id} prior"),
            )
        )
    with_ledgers = {row.head_id for row in ledgers}
    without = [h.id for h in heads if h.mappable and h.id not in with_ledgers]
    adjustments: list[SpineAdjustment] = []
    for raw in client.adjustments(version.version_id):
        raw_lines = [ln for ln in (raw.get("lines") or []) if isinstance(ln, dict)]
        if not any(ln.get("head_id") in covered for ln in raw_lines):
            continue
        adjustments.append(_adjustment_from(raw, raw_lines))
    return SpineBlock(
        kind="lead_schedule",
        version_id=version.version_id,
        version_label=version.label,
        version_hash=version.hash or "",
        locked_at=version.locked_at,
        balances_hash=_str_or_none(balances.get("hash"), "the balances hash"),
        tree_version=tree.version,
        area=code,
        lines=lines,
        ledgers=ledgers,
        head_totals=totals,
        heads_without_ledgers=without,
        adjustments=adjustments,
    )


def render_lead_schedule(block: SpineBlock, tree: SpineTree, area_name: str) -> str:
    """The lead schedule as markdown, every figure the Spine's own string. Where the Spine
    served no ledger or no figure, that is what the text says."""
    labels = {h.id: h.label for h in tree.heads}
    version = (
        f"Spine version {block.version_label} (`{block.version_id}`, hash `{block.version_hash}`)"
    )
    out: list[str] = [
        f"## {area_name}: financial statement lines",
        "",
        f"Figures as served by the Financial Spine, {version}.",
        "",
    ]
    if block.lines:
        out += ["| Line | Head | Current | Prior |", "|---|---|---|---|"]
        out += [
            _row(
                _cell(ln.label),
                f"`{ln.head_id}`",
                _cell(served(ln.current)),
                _cell(served(ln.prior)),
            )
            for ln in block.lines
        ]
    else:
        out.append(
            f"The presentation of {version} serves no financial statement line under this "
            "area's heads."
        )
    out += ["", "## Ledgers by head", ""]
    by_head: dict[str, list[SpineLedgerRow]] = {}
    for row in block.ledgers:
        by_head.setdefault(row.head_id, []).append(row)
    totals = {t.head_id: t for t in block.head_totals}
    heads_in_order = [
        h for h in tree.heads if h.id in by_head or h.id in block.heads_without_ledgers
    ]
    if not heads_in_order:
        out.append(
            "No head of this area carries a ledger in the Spine's balances, and none is listed "
            "as mappable."
        )
    for head in heads_in_order:
        rows = by_head.get(head.id)
        out.append(f"### {_cell(labels.get(head.id, head.id))} (`{head.id}`)")
        if not rows:
            line = next((ln for ln in block.lines if ln.head_id == head.id), None)
            figure = (
                f"presentation current {served(line.current)}, prior {served(line.prior)}"
                if line
                else "no presentation line served for this head"
            )
            out += ["", f"The balances of {version} list no ledger under this head; {figure}.", ""]
            continue
        total = totals.get(head.id)
        if total is not None:
            out += [
                "",
                f"Totals as served by the Spine: {total.ledgers} ledger(s); unadjusted "
                f"{served(total.unadjusted)}; adjusted {served(total.adjusted)}; prior "
                f"{served(total.prior_closing)}.",
                "",
            ]
        out += [
            _row(
                "Ledger",
                "Group chain",
                "Unadjusted",
                "Reclassifications",
                "Corrections",
                "Adjusted",
                "Prior",
            ),
            "|---|---|---|---|---|---|---|",
        ]
        out += [
            _row(
                _cell(r.ledger_name),
                _cell(" / ".join(r.parent_chain)),
                _cell(served(r.unadjusted)),
                _cell(served(r.reclass)),
                _cell(served(r.corrections)),
                _cell(served(r.adjusted)),
                _cell(served(r.prior_closing)),
            )
            for r in rows
        ]
        out.append("")
    out += ["## Adjustments touching this area", ""]
    if not block.adjustments:
        out.append("The Spine lists no adjustment with a line under this area's heads.")
    else:
        out += [
            _row(
                "Adjustment",
                "Kind",
                "Status",
                "Narration",
                "Working paper",
                "Lines on this area's heads",
            ),
            "|---|---|---|---|---|---|",
        ]
        for adj in block.adjustments:
            lines = "; ".join(
                f"`{ln.head_id}` dr {served(ln.dr)} cr {served(ln.cr)}"
                for ln in adj.lines
                if ln.head_id in {h.id for h in heads_in_order} or ln.head_id in by_head
            ) or "; ".join(
                f"`{ln.head_id}` dr {served(ln.dr)} cr {served(ln.cr)}" for ln in adj.lines
            )
            out.append(
                _row(
                    _cell(adj.adjustment_id),
                    _cell(adj.kind),
                    _cell(adj.status),
                    _cell(adj.narration),
                    _cell(adj.working_paper_ref) or "—",
                    _cell(lines),
                )
            )
    return "\n".join(out).rstrip() + "\n"


def _population(block: SpineBlock, version: SpineVersion, code: str) -> str:
    heads_with = len({r.head_id for r in block.ledgers})
    return (
        f"Spine version {version.label} ({version.version_id}), locked, hash {version.hash}: "
        f"{len(block.ledgers)} ledger row(s) served under {heads_with} head(s) of area {code}; "
        f"{len(block.heads_without_ledgers)} mappable head(s) with no ledger entry; "
        f"{len(block.lines)} financial statement line(s); {len(block.adjustments)} adjustment(s) "
        "touching the area. Figures are the Spine's, not retyped."
    )


def lead_schedule(
    session: Session,
    client: SpineClient | None,
    binder: Binder,
    code: str,
    *,
    user: str,
    now: datetime,
    max_bytes: int,
) -> Wp:
    """Generate area ``code``'s lead schedule from the linked, locked Spine version."""
    ready = readiness(client, binder)
    if not ready.ok or client is None or ready.version is None:
        raise ready.refuse("cannot generate Spine papers")
    version = ready.version
    template = load_template(binder.template)
    if code not in AREA_SECTIONS:
        raise Invalid(f"{code!r} is not a financial statement area D-T")
    tree = client.tree()
    resolved = area_map.resolve(template, tree)
    _require_area(resolved, template, code)
    checked = area_map.check_areas(resolved.areas, tree)
    if not checked.ok:
        raise Invalid(
            "the area map is refused against the Spine's tree: " + "; ".join(checked.problems)
        )
    area = resolved.areas[code]
    block = _block_for_area(client, version, tree, area, checked, code)
    area_name = resolved.names[code]
    paper = PaperFields(
        ref=lead_schedule_ref(code),
        section=code,
        title=f"Lead schedule: {area_name}",
        sa_refs=[],
        objective=area.objective,
        procedure=area.procedure,
        population_sample=_population(block, version, code),
        result=render_lead_schedule(block, tree, area_name),
        conclusion=None,
    )
    generated = Generated(
        source="spine",
        module=MODULE,
        module_version=None,
        run_id=f"{binder.id}/{version.version_id}/{version.hash}/{code}",
        generated_at=now,
        inputs={
            "version_id": str(version.version_id),
            "version_hash": version.hash,
            "area": code,
            "area_map_source": resolved.source,
            "listed_heads": list(area.heads),
            "covered_heads": sorted(checked.coverage[code]),
            "tree_version": tree.version,
            "read": ["version", "tree", "presentation", "balances", "adjustments"],
            "template_wording": {
                "objective": area.objective is not None,
                "procedure": area.procedure is not None,
            },
            "references_written": {"fs_lines": [ln.head_id for ln in block.lines]},
        },
        citations=[
            *(
                {
                    "source": "Financial Spine",
                    "version_id": str(version.version_id),
                    "head_id": ln.head_id,
                }
                for ln in block.lines
            ),
            *(
                {
                    "source": "Financial Spine",
                    "version_id": str(version.version_id),
                    "head_id": r.head_id,
                    "ledger_key": r.ledger_key,
                }
                for r in block.ledgers
            ),
            *(
                {
                    "source": "Financial Spine",
                    "version_id": str(version.version_id),
                    "adjustment_id": a.adjustment_id,
                }
                for a in block.adjustments
            ),
        ]
        or [{"source": "Financial Spine", "version_id": str(version.version_id), "area": code}],
        spine=block,
    )
    wp = generated_service.receive(
        session,
        binder,
        GeneratedPaperIn(paper=paper, generated=generated),
        user=user,
        now=now,
        max_bytes=max_bytes,
        allow_spine=True,
    )
    lines = fs_lines.for_binder(client, binder)
    for line in block.lines:
        xref_service.add(
            session,
            wp,
            to_wp=None,
            to_fs_line=line.head_id,
            to_vault_doc=None,
            direction="to",
            user=REFERENCE_CREATOR,
            now=now,
            lines=lines,
        )
    return wp


def lead_schedules(
    session: Session,
    client: SpineClient | None,
    binder: Binder,
    codes: list[str] | None,
    *,
    user: str,
    now: datetime,
    max_bytes: int,
) -> list[Wp]:
    """Generate the named areas' lead schedules, or, with ``codes`` None, every mapped area that
    has none yet. Every named area must succeed; one refusal fails the whole request."""
    if codes is None:
        ready = readiness(client, binder)
        if not ready.ok or client is None:
            raise ready.refuse("cannot generate Spine papers")
        template = load_template(binder.template)
        resolved = area_map.resolve(template, client.tree())
        existing = _lead_schedules(session, binder)
        codes = [c for c in AREA_SECTIONS if c in resolved.areas and c not in existing]
        if not codes:
            if not resolved.areas:
                raise Invalid(NO_AREAS.format(template=template.name))
            raise Conflict("every mapped area already has its lead schedule; nothing to generate")
    if not codes:
        raise Invalid("name at least one area, or omit 'areas' for every mapped area without one")
    seen: list[str] = []
    for code in codes:
        if code in seen:
            raise Invalid(f"area {code} is named twice")
        seen.append(code)
    return [
        lead_schedule(session, client, binder, code, user=user, now=now, max_bytes=max_bytes)
        for code in codes
    ]


# --- the adjustment chain (step E3) ------------------------------------------------------


def _chain_block(client: SpineClient, version: SpineVersion) -> SpineBlock:
    """Every adjustment of the version, in all three statuses, and the uncorrected schedule
    exactly as the Spine served it."""
    adjustments = [
        _adjustment_from(raw, [ln for ln in (raw.get("lines") or []) if isinstance(ln, dict)])
        for raw in client.adjustments(version.version_id)
        if isinstance(raw, dict)
    ]
    uncorrected = client.uncorrected(version.version_id)
    return SpineBlock(
        kind="adjustment_chain",
        version_id=version.version_id,
        version_label=version.label,
        version_hash=version.hash or "",
        locked_at=version.locked_at,
        adjustments=adjustments,
        uncorrected=uncorrected,
    )


def _as_served(value: Any) -> str:
    """A value from the uncorrected schedule, rendered without interpretation: a string as
    is, no value as "no figure served", anything else as its JSON text."""
    if value is None:
        return NO_FIGURE
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _render_served(title: str, value: Any, out: list[str]) -> None:
    """A section of the uncorrected schedule: a list of records as a table whose columns are
    the keys in the order they first appear; a record as a list of its keys; a scalar as is."""
    out += [f"### {title}", ""]
    if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
        keys: list[str] = []
        for item in value:
            keys += [k for k in item if k not in keys]
        out += [_row(*(_cell(k) for k in keys)), "|" + "---|" * len(keys)]
        out += [_row(*(_cell(_as_served(item.get(k))) for k in keys)) for item in value]
    elif isinstance(value, list):
        out += [f"- {_cell(_as_served(item))}" for item in value] or ["(none served)"]
    elif isinstance(value, dict):
        out += [f"- {_cell(k)}: {_cell(_as_served(v))}" for k, v in value.items()] or [
            "(none served)"
        ]
    else:
        out.append(_cell(_as_served(value)))
    out.append("")


def render_adjustment_chain(block: SpineBlock, matched: dict[str, Wp | None]) -> str:
    """The adjustment chain as markdown: the adjustments with their lines, the working papers
    they name (found in this binder or not), and the uncorrected schedule as served. Every
    figure is the Spine's string; nothing is summed, netted or compared here."""
    version = (
        f"Spine version {block.version_label} (`{block.version_id}`, hash `{block.version_hash}`)"
    )
    out: list[str] = [
        "## Adjustments",
        "",
        f"Every adjustment of {version}, in every status, as the Spine served it: "
        f"{len(block.adjustments)} adjustment(s).",
        "",
    ]
    if not block.adjustments:
        out.append("The Spine lists no adjustment on this version.")
    else:
        out += [
            _row(
                "Adjustment",
                "Kind",
                "Status",
                "Narration",
                "Working paper",
                "Finding",
                "Proposed",
                "Decided",
                "Decision note",
            ),
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for adj in block.adjustments:
            out.append(
                _row(
                    _cell(adj.adjustment_id),
                    _cell(adj.kind),
                    _cell(adj.status),
                    _cell(adj.narration),
                    _cell(adj.working_paper_ref) or "—",
                    _cell(adj.finding_ref) or "—",
                    _cell(" ".join(p for p in (adj.proposed_by, adj.proposed_at) if p)),
                    _cell(" ".join(p for p in (adj.decided_by, adj.decided_at) if p)) or "—",
                    _cell(adj.decision_note) or "—",
                )
            )
        for adj in block.adjustments:
            out += ["", f"### {_cell(adj.adjustment_id)}: lines", ""]
            if not adj.lines:
                out.append("No lines served.")
                continue
            out += [_row("Line", "Ledger", "Head", "Dr", "Cr"), "|---|---|---|---|---|"]
            out += [
                _row(
                    _cell(str(ln.line_no) if ln.line_no is not None else ""),
                    _cell(ln.ledger_name or ln.ledger_key),
                    f"`{ln.head_id}`" if ln.head_id else "—",
                    _cell(served(ln.dr)),
                    _cell(served(ln.cr)),
                )
                for ln in adj.lines
            ]
    out += ["", "## Working papers named by the adjustments", ""]
    if not matched:
        out.append("No adjustment names a working paper.")
    else:
        out += [_row("Reference", "In this binder"), "|---|---|"]
        for ref, paper in matched.items():
            where = (
                f"paper {paper.ref}: {_cell(paper.title)}"
                if paper is not None
                else "no paper of this binder with that reference"
            )
            out.append(_row(_cell(ref), where))
        out += [
            "",
            "A reference is matched by exact text only; a name that matches no paper "
            "is listed, never guessed (decision 7).",
        ]
    out += ["", "## Uncorrected misstatements, as served", ""]
    uncorrected = block.uncorrected or {}
    scalars = {k: v for k, v in uncorrected.items() if not isinstance(v, list | dict)}
    if scalars:
        out += [f"- {_cell(k)}: {_cell(_as_served(v))}" for k, v in scalars.items()]
        out.append("")
    for key, value in uncorrected.items():
        if isinstance(value, list | dict):
            _render_served(key, value, out)
    if not uncorrected:
        out.append("The Spine served no uncorrected schedule.")
    return "\n".join(out).rstrip() + "\n"


def _match_working_papers(
    session: Session, binder: Binder, block: SpineBlock
) -> dict[str, Wp | None]:
    """Each working-paper reference the adjustments name, in first-seen order, with the paper
    of this binder whose reference is exactly that text, or None."""
    names: list[str] = []
    for adj in block.adjustments:
        if adj.working_paper_ref and adj.working_paper_ref not in names:
            names.append(adj.working_paper_ref)
    if not names:
        return {}
    papers = {
        p.ref: p
        for p in session.scalars(
            select(Wp).where(Wp.binder_id == binder.id, Wp.ref.in_(names))
        ).all()
    }
    return {name: papers.get(name) for name in names}


def _population_chain(block: SpineBlock, version: SpineVersion) -> str:
    uncorrected = block.uncorrected or {}
    listed = uncorrected.get("uncorrected")
    count = len(listed) if isinstance(listed, list) else 0
    by_status: dict[str, int] = {}
    for adj in block.adjustments:
        by_status[adj.status] = by_status.get(adj.status, 0) + 1
    statuses = ", ".join(f"{n} {status}" for status, n in sorted(by_status.items())) or "none"
    return (
        f"Spine version {version.label} ({version.version_id}), locked, hash {version.hash}: "
        f"{len(block.adjustments)} adjustment(s) served ({statuses}); {count} uncorrected "
        "misstatement(s) listed by the Spine. Figures and the schedule are the Spine's, not "
        "retyped."
    )


def adjustment_chain(
    session: Session,
    client: SpineClient | None,
    binder: Binder,
    *,
    user: str,
    now: datetime,
    max_bytes: int,
) -> Wp:
    """Generate the binder's adjustment-chain paper, ``W-ADJ`` in section W, from the linked,
    locked Spine version. One per binder: a repeat on an unchanged version is refused as one
    paper per run, naming the existing paper."""
    ready = readiness(client, binder)
    if not ready.ok or client is None or ready.version is None:
        raise ready.refuse("cannot generate Spine papers")
    version = ready.version
    block = _chain_block(client, version)
    matched = _match_working_papers(session, binder, block)
    paper = PaperFields(
        ref=CHAIN_REF,
        section=CHAIN_SECTION,
        title="Adjustment chain and uncorrected misstatements",
        sa_refs=[],
        objective=None,
        procedure=None,
        population_sample=_population_chain(block, version),
        result=render_adjustment_chain(block, matched),
        conclusion=None,
    )
    generated = Generated(
        source="spine",
        module=MODULE,
        module_version=None,
        run_id=f"{binder.id}/{version.version_id}/{version.hash}/adjustments",
        generated_at=now,
        inputs={
            "version_id": str(version.version_id),
            "version_hash": version.hash,
            "kind": "adjustment_chain",
            "read": ["version", "adjustments", "uncorrected"],
            "working_paper_refs": {name: (p.ref if p else None) for name, p in matched.items()},
            "references_written": {"papers": [p.ref for p in matched.values() if p is not None]},
        },
        citations=[
            *(
                {
                    "source": "Financial Spine",
                    "version_id": str(version.version_id),
                    "adjustment_id": a.adjustment_id,
                }
                for a in block.adjustments
            ),
            {
                "source": "Financial Spine",
                "version_id": str(version.version_id),
                "endpoint": "uncorrected",
            },
        ],
        spine=block,
    )
    wp = generated_service.receive(
        session,
        binder,
        GeneratedPaperIn(paper=paper, generated=generated),
        user=user,
        now=now,
        max_bytes=max_bytes,
        allow_spine=True,
    )
    for target in matched.values():
        if target is None or target.id == wp.id:
            continue
        xref_service.add(
            session,
            wp,
            to_wp=target.id,
            to_fs_line=None,
            to_vault_doc=None,
            direction="to",
            user=REFERENCE_CREATOR,
            now=now,
        )
    return wp


# --- regeneration (step E4) ---------------------------------------------------------------------


@dataclass(frozen=True)
class ReferencePlan:
    """What regeneration does to the paper's references, decided before anything is written
    and recorded in the new provenance row. Only a reference the Binder reliably owns is ever
    removed: created by the Spine marker and pointing at a target a previous Spine block of
    this paper named. Everything else is kept; a kept reference whose target the new block
    lacks is listed for a person's review."""

    added: tuple[str, ...]
    removed: tuple[str, ...]
    kept: tuple[str, ...]
    for_review: tuple[str, ...]

    def record(self) -> dict[str, list[str]]:
        return {
            "added": list(self.added),
            "removed": list(self.removed),
            "kept": list(self.kept),
            "for_review": list(self.for_review),
        }


@dataclass(frozen=True)
class Regeneration:
    paper: Wp
    generation: WpGeneration
    references: ReferencePlan


def _previous_targets(session: Session, paper: Wp) -> set[str]:
    """Targets any earlier Spine block of this paper named: FS-line head ids and the
    references of matched working papers."""
    targets: set[str] = set()
    for row in session.scalars(
        select(WpGeneration)
        .where(WpGeneration.wp_id == paper.id, WpGeneration.source == "spine")
        .order_by(WpGeneration.received_at, WpGeneration.id)
    ).all():
        block = _block_of(row)
        for line in block.get("lines") or []:
            if isinstance(line, dict) and isinstance(line.get("head_id"), str):
                targets.add(line["head_id"])
        inputs = row.payload.get("inputs") if isinstance(row.payload, dict) else None
        written = inputs.get("references_written") if isinstance(inputs, dict) else None
        if isinstance(written, dict):
            for ref in written.get("papers") or []:
                if isinstance(ref, str):
                    targets.add(ref)
        refs = inputs.get("working_paper_refs") if isinstance(inputs, dict) else None
        if isinstance(refs, dict):
            for matched in refs.values():
                if isinstance(matched, str):
                    targets.add(matched)
    return targets


def _target_of(session: Session, xref: Any) -> str | None:
    """A reference's target as the plan names it: the FS line's head id, or the paper's ref."""
    if xref.to_fs_line is not None:
        return str(xref.to_fs_line)
    if xref.to_wp is not None:
        target = session.get(Wp, xref.to_wp)
        return target.ref if target else None
    return None


def plan_references(
    session: Session, paper: Wp, new_targets: list[str], previous_targets: set[str]
) -> tuple[ReferencePlan, list[Any]]:
    """Classify the paper's outgoing references against the new block's targets; return the
    plan and the reference rows to remove."""
    existing = [
        x
        for x in xref_service.for_paper(session, paper)
        if x.from_wp == paper.id and x.direction == "to" and x.to_vault_doc is None
    ]
    wanted = set(new_targets)
    present: set[str] = set()
    kept: list[str] = []
    removed: list[str] = []
    review: list[str] = []
    to_remove: list[Any] = []
    for x in existing:
        target = _target_of(session, x)
        if target is None:
            continue
        if target in wanted:
            present.add(target)
            kept.append(target)
            continue
        owned = x.created_by == REFERENCE_CREATOR and target in previous_targets
        if owned:
            removed.append(target)
            to_remove.append(x)
        else:
            review.append(target)
    added = [t for t in new_targets if t not in present]
    # The record names targets, once each in first-seen order; the rows to remove stay one per
    # reference, so a target with both a Binder-written and a person's reference is reported
    # once and both rows are handled as classified.
    return ReferencePlan(
        _unique(added), _unique(removed), _unique(kept), _unique(review)
    ), to_remove


def _unique(targets: list[str]) -> tuple[str, ...]:
    seen: list[str] = []
    for target in targets:
        if target not in seen:
            seen.append(target)
    return tuple(seen)


def regenerate(
    session: Session,
    client: SpineClient | None,
    binder: Binder,
    paper: Wp,
    *,
    user: str,
    now: datetime,
    max_bytes: int,
) -> Regeneration:
    """Rebuild a Spine paper from the binder's linked, locked version: the Spine's fields are
    rewritten, the paper returns to draft, a new provenance row is appended, and the Binder's
    own references follow the new block. The person's objective, procedure and conclusion and
    every earlier version are kept. Open binders only (decision 15)."""
    previous = paper_service.latest_generation(session, paper)
    if previous is None or previous.source != "spine":
        raise Invalid(f"paper {paper.ref} was not generated from the Financial Spine")
    ready = readiness(client, binder)
    if not ready.ok or client is None or ready.version is None:
        raise ready.refuse("cannot regenerate")
    version = ready.version
    kind = _block_of(previous).get("kind")
    if kind == "lead_schedule":
        code = str(_block_of(previous).get("area") or "")
        template = load_template(binder.template)
        tree = client.tree()
        resolved = area_map.resolve(template, tree)
        if code not in resolved.areas:
            raise Invalid(
                f"area {code} has no Schedule III heads in the area map in force for template "
                f"{template.name} ({resolved.source}); the lead schedule cannot be regenerated"
            )
        checked = area_map.check_areas(resolved.areas, tree)
        if not checked.ok:
            raise Invalid(
                "the area map is refused against the Spine's tree: " + "; ".join(checked.problems)
            )
        area = resolved.areas[code]
        block = _block_for_area(client, version, tree, area, checked, code)
        area_name = resolved.names[code]
        fields = PaperFields(
            ref=paper.ref,
            section=code,
            title=f"Lead schedule: {area_name}",
            sa_refs=[],
            objective=paper.objective,
            procedure=paper.procedure,
            population_sample=_population(block, version, code),
            result=render_lead_schedule(block, tree, area_name),
            conclusion=paper.conclusion,
        )
        new_targets = [ln.head_id for ln in block.lines]
        run_id = f"{binder.id}/{version.version_id}/{version.hash}/{code}"
        inputs: dict[str, Any] = {
            "version_id": str(version.version_id),
            "version_hash": version.hash,
            "area": code,
            "area_map_source": resolved.source,
            "listed_heads": list(area.heads),
            "covered_heads": sorted(checked.coverage[code]),
            "tree_version": tree.version,
            "read": ["version", "tree", "presentation", "balances", "adjustments"],
            "references_written": {"fs_lines": new_targets},
        }
        citations: list[Any] = [
            {"source": "Financial Spine", "version_id": str(version.version_id), "head_id": h}
            for h in new_targets
        ] or [{"source": "Financial Spine", "version_id": str(version.version_id), "area": code}]
        matched: dict[str, Wp | None] = {}
    elif kind == "adjustment_chain":
        block = _chain_block(client, version)
        matched = _match_working_papers(session, binder, block)
        fields = PaperFields(
            ref=paper.ref,
            section=CHAIN_SECTION,
            title="Adjustment chain and uncorrected misstatements",
            sa_refs=[],
            objective=paper.objective,
            procedure=paper.procedure,
            population_sample=_population_chain(block, version),
            result=render_adjustment_chain(block, matched),
            conclusion=paper.conclusion,
        )
        new_targets = [p.ref for p in matched.values() if p is not None and p.id != paper.id]
        run_id = f"{binder.id}/{version.version_id}/{version.hash}/adjustments"
        inputs = {
            "version_id": str(version.version_id),
            "version_hash": version.hash,
            "kind": "adjustment_chain",
            "read": ["version", "adjustments", "uncorrected"],
            "working_paper_refs": {name: (p.ref if p else None) for name, p in matched.items()},
            "references_written": {"papers": new_targets},
        }
        citations = [
            {
                "source": "Financial Spine",
                "version_id": str(version.version_id),
                "adjustment_id": a.adjustment_id,
            }
            for a in block.adjustments
        ] + [
            {
                "source": "Financial Spine",
                "version_id": str(version.version_id),
                "endpoint": "uncorrected",
            }
        ]
    else:
        raise Invalid(f"paper {paper.ref} carries an unknown Spine block kind {kind!r}")

    plan, to_remove = plan_references(
        session, paper, new_targets, _previous_targets(session, paper)
    )
    inputs["regeneration"] = {
        "previous_run_id": previous.run_id,
        "previous_version_id": _block_of(previous).get("version_id"),
        "previous_version_hash": _block_of(previous).get("version_hash"),
        "references": plan.record(),
        "kept_by_person": ["objective", "procedure", "conclusion"],
    }
    generated = Generated(
        source="spine",
        module=MODULE,
        module_version=None,
        run_id=run_id,
        generated_at=now,
        inputs=inputs,
        citations=citations,
        spine=block,
    )
    row = generated_service.regenerate(
        session,
        paper,
        GeneratedPaperIn(paper=fields, generated=generated),
        user=user,
        now=now,
        max_bytes=max_bytes,
    )
    for x in to_remove:
        xref_service.remove(session, x)
    if kind == "lead_schedule":
        lines = fs_lines.for_binder(client, binder)
        for head_id in plan.added:
            xref_service.add(
                session,
                paper,
                to_wp=None,
                to_fs_line=head_id,
                to_vault_doc=None,
                direction="to",
                user=REFERENCE_CREATOR,
                now=now,
                lines=lines,
            )
    else:
        by_ref = {p.ref: p for p in matched.values() if p is not None}
        for ref in plan.added:
            target = by_ref[ref]
            xref_service.add(
                session,
                paper,
                to_wp=target.id,
                to_fs_line=None,
                to_vault_doc=None,
                direction="to",
                user=REFERENCE_CREATOR,
                now=now,
            )
    return Regeneration(paper, row, plan)
