"""Binders: creation from a template, the report date and its clocks, the index tree and the
completeness view (spec 3A, 3F, 3G, 5.1)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from oak_binder.clocks import assembly_due, retention_until
from oak_binder.errors import Conflict, Invalid, NotFound
from oak_binder.models import Binder, BinderState, Wp
from oak_binder.services.templates import IndexTemplate, RequiredPaper, load_template


def create_binder(
    session: Session, *, engagement: str, template: str, report_date: date | None
) -> Binder:
    engagement = engagement.strip()
    if not engagement:
        raise Invalid("engagement must not be blank")
    try:
        load_template(template)
    except NotFound as exc:
        # On creation the template is request content, not a resource being looked up.
        raise Invalid(str(exc)) from exc
    binder = Binder(engagement=engagement, template=template, state=BinderState.OPEN)
    _apply_report_date(binder, report_date)
    session.add(binder)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        if "uq_binder_engagement" in str(exc):
            raise Conflict(f"a binder already exists for engagement {engagement!r}") from exc
        raise
    return binder


def get_binder(session: Session, binder_id: uuid.UUID) -> Binder:
    binder = session.get(Binder, binder_id)
    if binder is None:
        raise NotFound(f"no binder {binder_id}")
    return binder


def list_binders(session: Session) -> list[Binder]:
    return list(session.scalars(select(Binder).order_by(Binder.created_at)).all())


def set_report_date(session: Session, binder: Binder, report_date: date | None) -> Binder:
    """Date (or undate) the report. Both clocks follow from it; the database re-checks them."""
    require_open(binder)
    _apply_report_date(binder, report_date)
    session.flush()
    return binder


def require_open(binder: Binder) -> None:
    if binder.state == BinderState.PURGED:
        raise Conflict(
            f"binder for {binder.engagement!r} was purged after retention; "
            "its content is gone and nothing can be changed"
        )
    if binder.state != BinderState.OPEN:
        raise Conflict(
            f"binder for {binder.engagement!r} is assembled; a post-assembly change is an "
            "amendment and needs a reason (spec 3F)"
        )


def _apply_report_date(binder: Binder, report_date: date | None) -> None:
    binder.report_date = report_date
    binder.assembly_due = assembly_due(report_date) if report_date else None
    binder.retention_until = retention_until(report_date) if report_date else None


# --- the index and completeness view -----------------------------------------------------------


@dataclass
class SectionIndex:
    code: str
    name: str
    papers: list[Wp] = field(default_factory=list)
    missing: list[RequiredPaper] = field(default_factory=list)


@dataclass
class BinderIndex:
    template: IndexTemplate
    sections: list[SectionIndex]

    @property
    def missing_required(self) -> int:
        """The blocking count (spec 3A): required papers with no paper at their reference."""
        return sum(len(s.missing) for s in self.sections)


def build_index(session: Session, binder: Binder) -> BinderIndex:
    template = load_template(binder.template)
    papers = session.scalars(
        select(Wp).where(Wp.binder_id == binder.id).order_by(Wp.section, Wp.ref)
    ).all()
    by_section: dict[str, SectionIndex] = {
        s.code: SectionIndex(s.code, s.name) for s in template.sections
    }
    # A required paper counts as present only at its reference in its section (spec 3A:
    # "missing, per section"); a paper filed under the right reference in another section
    # still leaves the requirement open.
    present = {(p.ref, p.section) for p in papers}
    for paper in papers:
        by_section.setdefault(
            paper.section, SectionIndex(paper.section, f"Section {paper.section}")
        ).papers.append(paper)
    for required in template.required:
        if (required.ref, required.section) not in present:
            by_section[required.section].missing.append(required)
    return BinderIndex(template, list(by_section.values()))
