from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from oak_binder.models import Wp, WpAttachment, WpVersion
from oak_binder.schemas.attachments import AttachmentOut
from oak_binder.schemas.xrefs import XrefOut


class PaperCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: str
    section: str
    title: str
    sa_refs: list[str] = []
    objective: str | None = None
    procedure: str | None = None
    population_sample: str | None = None
    result: str | None = None
    conclusion: str | None = None


class PaperPatch(BaseModel):
    """Every field optional; only fields present in the request are changed. ``ref`` is
    deliberately absent and unknown fields are refused, so a request that tries to change
    the reference fails instead of being silently ignored (spec 3B)."""

    model_config = ConfigDict(extra="forbid")

    section: str | None = None
    title: str | None = None
    sa_refs: list[str] | None = None
    objective: str | None = None
    procedure: str | None = None
    population_sample: str | None = None
    result: str | None = None
    conclusion: str | None = None
    # Required once the binder is assembled: the change becomes an amendment (spec 3F).
    amendment_reason: str | None = None


class VersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version: int
    body: dict[str, Any]
    prepared_by: str
    prepared_at: datetime
    reviewed_by: str | None
    reviewed_at: datetime | None
    signed_off_by: str | None
    signed_off_at: datetime | None
    content_hash: str
    amendment_reason: str | None


class PaperSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ref: str
    section: str
    title: str
    status: str
    current_version: int | None


class PaperOut(PaperSummary):
    binder_id: uuid.UUID
    sa_refs: list[str]
    objective: str | None
    procedure: str | None
    population_sample: str | None
    result: str | None
    conclusion: str | None
    created_at: datetime
    binder_state: str
    open_review_notes: int
    versions: list[VersionOut]
    attachments: list[AttachmentOut]
    # Spec 3B: cross-references in and out, read from this paper.
    xrefs: list[XrefOut]

    @classmethod
    def build(
        cls,
        paper: Wp,
        versions: list[WpVersion],
        attachments: list[WpAttachment],
        binder_state: str,
        open_review_notes: int = 0,
        xrefs: list[XrefOut] | None = None,
    ) -> PaperOut:
        base = PaperSummary.model_validate(paper).model_dump()
        return cls(
            **base,
            binder_id=paper.binder_id,
            sa_refs=list(paper.sa_refs),
            objective=paper.objective,
            procedure=paper.procedure,
            population_sample=paper.population_sample,
            result=paper.result,
            conclusion=paper.conclusion,
            created_at=paper.created_at,
            binder_state=binder_state,
            open_review_notes=open_review_notes,
            versions=[VersionOut.model_validate(v) for v in versions],
            attachments=[AttachmentOut.model_validate(a) for a in attachments],
            xrefs=xrefs or [],
        )
