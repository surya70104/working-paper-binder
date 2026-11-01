from __future__ import annotations

import uuid

from pydantic import BaseModel

from oak_binder.services.fs_lines import FsLines
from oak_binder.services.xref_map import MapDocument, MapLine, MapLink, MapPaper, XrefMap


class FsLineOut(BaseModel):
    head_id: str
    label: str
    side: str | None
    depth: int | None
    item: str | None
    current: str | None
    prior: str | None
    has_figures: bool


class FsLinesOut(BaseModel):
    """The lines a reference may name, or why there are none (spec 3E; D30)."""

    available: bool
    reason: str | None
    version_locked: bool
    lines: list[FsLineOut]

    @classmethod
    def build(cls, lines: FsLines) -> FsLinesOut:
        return cls(
            available=lines.available,
            reason=lines.reason,
            version_locked=lines.version_locked,
            lines=[
                FsLineOut(
                    head_id=line.head_id,
                    label=line.label,
                    side=line.side,
                    depth=line.depth,
                    item=line.item,
                    current=line.current,
                    prior=line.prior,
                    has_figures=line.has_figures,
                )
                for line in lines.lines.values()
            ],
        )


class MapLinkOut(BaseModel):
    xref_id: uuid.UUID
    direction: str
    broken: str | None
    amended: str | None
    checked: bool

    @classmethod
    def build(cls, link: MapLink) -> MapLinkOut:
        return cls(
            xref_id=link.xref_id,
            direction=link.direction,
            broken=link.broken,
            amended=link.amended,
            checked=link.checked,
        )


class MapDocumentOut(BaseModel):
    xref_id: uuid.UUID
    doc_id: str
    attachment_id: uuid.UUID | None
    filename: str | None
    filed_on_ref: str | None
    broken: str | None

    @classmethod
    def build(cls, d: MapDocument) -> MapDocumentOut:
        return cls(
            xref_id=d.xref_id,
            doc_id=d.doc_id,
            attachment_id=d.attachment_id,
            filename=d.filename,
            filed_on_ref=d.filed_on_ref,
            broken=d.broken,
        )


class MapPaperOut(BaseModel):
    id: uuid.UUID
    ref: str
    title: str
    section: str
    status: str
    role: str
    link: MapLinkOut | None
    documents: list[MapDocumentOut]
    papers: list[MapPaperOut]

    @classmethod
    def build(cls, p: MapPaper) -> MapPaperOut:
        return cls(
            id=p.id,
            ref=p.ref,
            title=p.title,
            section=p.section,
            status=p.status,
            role=p.role,
            link=MapLinkOut.build(p.link) if p.link else None,
            documents=[MapDocumentOut.build(d) for d in p.documents],
            papers=[MapPaperOut.build(q) for q in p.papers],
        )


class MapLineOut(BaseModel):
    head_id: str
    label: str | None
    side: str | None
    current: str | None
    prior: str | None
    known: bool
    papers: list[MapPaperOut]

    @classmethod
    def build(cls, line: MapLine) -> MapLineOut:
        return cls(
            head_id=line.head_id,
            label=line.label,
            side=line.side,
            current=line.current,
            prior=line.prior,
            known=line.known,
            papers=[MapPaperOut.build(p) for p in line.papers],
        )


class XrefMapOut(BaseModel):
    """Screen 4 (spec 5): FS line to lead schedule to paper to document, with broken and
    amended links flagged."""

    available: bool
    reason: str | None
    lines: list[MapLineOut]
    beyond_depth: list[MapPaperOut]
    unattached: list[MapPaperOut]
    max_depth: int
    broken: int
    amended: int
    unchecked: int
    total_references: int

    @classmethod
    def build(cls, m: XrefMap) -> XrefMapOut:
        return cls(
            available=m.available,
            reason=m.reason,
            lines=[MapLineOut.build(line) for line in m.lines],
            beyond_depth=[MapPaperOut.build(p) for p in m.beyond_depth],
            unattached=[MapPaperOut.build(p) for p in m.unattached],
            max_depth=m.max_depth,
            broken=m.broken,
            amended=m.amended,
            unchecked=m.unchecked,
            total_references=m.total_references,
        )
