from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from oak_binder.clocks import days_to_assembly
from oak_binder.models import Binder
from oak_binder.schemas.papers import PaperSummary
from oak_binder.schemas.templates import RequiredPaperOut
from oak_binder.services.binders import BinderIndex


class BinderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    engagement: str
    template: str
    report_date: date | None = None


class BinderPatch(BaseModel):
    """Setting ``report_date`` sets both clocks; ``null`` clears all three. The Spine ids
    set, change or clear the link (D29): only the fields sent change."""

    model_config = ConfigDict(extra="forbid")

    report_date: date | None = None
    spine_engagement_id: uuid.UUID | None = None
    spine_version_id: uuid.UUID | None = None
    # Stage F (D33): the review levels after the preparer, in order; null or [] means the
    # Pass 1 chain. Changeable while open and before any level review is recorded.
    review_levels: list[str] | None = None


class BinderSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    engagement: str
    template: str
    report_date: date | None
    assembly_due: date | None
    retention_until: date | None
    assembled_at: datetime | None
    assembly_hash: str | None
    state: str
    created_at: datetime
    spine_engagement_id: uuid.UUID | None = None
    spine_version_id: uuid.UUID | None = None
    review_levels: list[str] | None = None


class SectionIndexOut(BaseModel):
    code: str
    name: str
    papers: list[PaperSummary]
    missing: list[RequiredPaperOut]


class BinderOut(BinderSummary):
    template_label: str
    days_to_assembly: int | None
    missing_required: int
    sections: list[SectionIndexOut]
    # Stage F (D33): true once a level review exists for a paper of this binder.
    review_levels_frozen: bool = False

    @classmethod
    def build(
        cls, binder: Binder, index: BinderIndex, today: date, review_levels_frozen: bool = False
    ) -> BinderOut:
        base = BinderSummary.model_validate(binder).model_dump()
        return cls(
            **base,
            template_label=index.template.label,
            days_to_assembly=(
                days_to_assembly(binder.assembly_due, today) if binder.assembly_due else None
            ),
            missing_required=index.missing_required,
            review_levels_frozen=review_levels_frozen,
            sections=[
                SectionIndexOut(
                    code=s.code,
                    name=s.name,
                    papers=[
                        PaperSummary.model_validate(p).model_copy(
                            update={"generated_by": index.generated_by.get(p.id)}
                        )
                        for p in s.papers
                    ],
                    missing=[
                        RequiredPaperOut(
                            ref=r.ref, section=r.section, title=r.title, sa_refs=list(r.sa_refs)
                        )
                        for r in s.missing
                    ],
                )
                for s in index.sections
            ],
        )
