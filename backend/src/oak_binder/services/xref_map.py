"""The cross-reference map (spec 5.4, 3E; D30): financial statement line → lead schedule →
working paper → source document, with broken and amended links flagged.

Built from the references alone. A paper that refers to a financial-statement line is the
lead schedule for that line (spec 3A: the lead schedule ties to the Spine, with the working
papers beneath it); the papers that refer to the lead schedule sit beneath it; each paper's
document references are its source documents. Papers that appear nowhere in that chain are
listed apart, so nothing in the file is hidden by the map.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from oak_binder.models import Binder, Wp, WpAttachment, Xref
from oak_binder.models.xref import Direction
from oak_binder.services import xrefs as xref_service
from oak_binder.services.fs_lines import FsLines

MAX_DEPTH = 3  # lead schedule, working paper, paper beneath that: the spec's chain and one more


@dataclass
class MapLink:
    xref_id: uuid.UUID
    direction: str
    broken: str | None
    amended: str | None
    checked: bool


@dataclass
class MapDocument:
    xref_id: uuid.UUID
    doc_id: str
    attachment_id: uuid.UUID | None
    filename: str | None
    filed_on_ref: str | None
    broken: str | None


@dataclass
class MapPaper:
    id: uuid.UUID
    ref: str
    title: str
    section: str
    status: str
    role: str  # "lead_schedule" or "working_paper"
    link: MapLink | None
    documents: list[MapDocument] = field(default_factory=list)
    papers: list[MapPaper] = field(default_factory=list)


@dataclass
class MapLine:
    head_id: str
    label: str | None
    side: str | None
    current: str | None
    prior: str | None
    known: bool  # the linked version has this line; False means free text or a vanished line
    papers: list[MapPaper] = field(default_factory=list)


@dataclass
class XrefMap:
    available: bool
    reason: str | None
    lines: list[MapLine]
    beyond_depth: list[MapPaper]  # tied to a line through the chain, deeper than it is drawn
    unattached: list[MapPaper]  # reachable from no line at all
    max_depth: int
    broken: int
    amended: int
    unchecked: int
    total_references: int


def _paper_node(session: Session, paper: Wp, role: str, link: MapLink | None) -> MapPaper:
    return MapPaper(paper.id, paper.ref, paper.title, paper.section, paper.status, role, link)


def _documents(
    session: Session, binder: Binder, paper: Wp, refs: list[Xref], lines: FsLines
) -> list[MapDocument]:
    found: list[MapDocument] = []
    for x in refs:
        if x.from_wp != paper.id or x.to_vault_doc is None:
            continue
        filed = xref_service.document_attachment(session, binder, x.to_vault_doc)
        filed_on = session.get(Wp, filed.wp_id) if filed is not None else None
        found.append(
            MapDocument(
                x.id,
                x.to_vault_doc,
                filed.id if filed else None,
                filed.filename if filed else None,
                filed_on.ref if filed_on else None,
                xref_service.check(session, binder, x, lines),
            )
        )
    return found


def _beneath(paper: Wp, refs: list[Xref]) -> list[tuple[Xref, uuid.UUID]]:
    """References that read 'some paper refers to this paper': rows pointing here with
    direction 'to', and rows written here with direction 'from'."""
    out: list[tuple[Xref, uuid.UUID]] = []
    for x in refs:
        if x.to_wp == paper.id and x.direction == Direction.TO:
            out.append((x, x.from_wp))
        elif x.from_wp == paper.id and x.direction == Direction.FROM and x.to_wp is not None:
            out.append((x, x.to_wp))
    return out


def build(session: Session, binder: Binder, lines: FsLines) -> XrefMap:
    refs = xref_service.for_binder(session, binder)
    papers = {
        p.id: p
        for p in session.scalars(select(Wp).where(Wp.binder_id == binder.id).order_by(Wp.ref)).all()
    }
    seen: set[uuid.UUID] = set()
    beyond: list[MapPaper] = []
    broken = amended = unchecked = 0

    def link_of(x: Xref) -> MapLink:
        nonlocal broken, amended, unchecked
        reason = xref_service.check(session, binder, x, lines)
        changed = xref_service.target_amended(session, x)
        checked = x.to_fs_line is None or lines.available
        if reason:
            broken += 1
        if changed:
            amended += 1
        if not checked:
            unchecked += 1
        return MapLink(x.id, x.direction, reason, changed, checked)

    def expand(paper: Wp, role: str, link: MapLink | None, depth: int) -> MapPaper:
        nonlocal broken
        node = _paper_node(session, paper, role, link)
        seen.add(paper.id)
        docs = _documents(session, binder, paper, refs, lines)
        for d in docs:
            if d.broken:
                broken += 1
        node.documents = docs
        for x, below_id in _beneath(paper, refs):
            below = papers.get(below_id)
            if below is None or below.id in seen:
                continue
            if depth < MAX_DEPTH:
                node.papers.append(expand(below, "working_paper", link_of(x), depth + 1))
            else:
                # Still part of this line's chain, only deeper than the map draws: listed
                # apart as such, never as a paper tied to no line. Its own chain is walked
                # the same way so nothing beneath it is mislabelled either.
                beyond.append(expand(below, "working_paper", link_of(x), depth + 1))
        return node

    by_line: dict[str, MapLine] = {}
    for x in refs:
        if x.to_fs_line is None:
            continue
        source = papers.get(x.from_wp)
        if source is None:
            continue
        head_id = x.to_fs_line
        if head_id not in by_line:
            line = lines.lines.get(head_id)
            by_line[head_id] = MapLine(
                head_id,
                line.label if line else None,
                line.side if line else None,
                line.current if line else None,
                line.prior if line else None,
                known=line is not None,
            )
        by_line[head_id].papers.append(expand(source, "lead_schedule", link_of(x), 1))

    # Known lines in the Spine's own order, then free-text or vanished lines, then any line
    # referenced but unknown.
    ordered: list[MapLine] = []
    for head_id in lines.lines:
        if head_id in by_line:
            ordered.append(by_line.pop(head_id))
    ordered.extend(by_line.values())

    unattached = [
        _paper_node(session, p, "working_paper", None) for p in papers.values() if p.id not in seen
    ]
    for node in unattached:
        node.documents = _documents(session, binder, papers[node.id], refs, lines)
    # Document references on unattached papers count towards the totals too.
    for node in unattached:
        broken += sum(1 for d in node.documents if d.broken)
    beyond.sort(key=lambda p: p.ref)
    return XrefMap(
        lines.available,
        lines.reason,
        ordered,
        beyond,
        unattached,
        MAX_DEPTH,
        broken,
        amended,
        unchecked,
        len(refs),
    )


def attachments_of(session: Session, paper: Wp) -> list[WpAttachment]:
    return list(session.scalars(select(WpAttachment).where(WpAttachment.wp_id == paper.id)).all())
