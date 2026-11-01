"""Spine papers (Stage E, D32): the status of the lead schedules per area and the request to
generate them."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict

from oak_binder.services.spine_papers import AreaStatus, ChainStatus, SpinePapersStatus


class LeadSchedulesIn(BaseModel):
    """Which areas to generate; omit ``areas`` (or send null) for every mapped area that has
    no lead schedule yet."""

    model_config = ConfigDict(extra="forbid")

    areas: list[str] | None = None


class AreaStatusOut(BaseModel):
    code: str
    name: str
    mapped: bool
    listed_heads: list[str]
    paper_id: uuid.UUID | None
    ref: str
    state: str  # none | current | stale | not_checked
    detail: str | None
    recorded_version_id: uuid.UUID | None = None
    recorded_version_label: str | None = None

    @classmethod
    def build(cls, a: AreaStatus) -> AreaStatusOut:
        return cls(
            code=a.code,
            name=a.name,
            mapped=a.mapped,
            listed_heads=list(a.listed_heads),
            paper_id=a.paper_id,
            ref=a.ref,
            state=a.state,
            detail=a.detail,
            recorded_version_id=a.recorded_version_id,
            recorded_version_label=a.recorded_version_label,
        )


class ChainStatusOut(BaseModel):
    """The adjustment-chain paper (E3): one per binder, in section W."""

    ref: str
    section: str
    paper_id: uuid.UUID | None
    state: str  # none | current | stale | not_checked
    can_generate: bool
    reason: str | None
    detail: str | None = None
    recorded_version_id: uuid.UUID | None = None
    recorded_version_label: str | None = None

    @classmethod
    def build(cls, c: ChainStatus) -> ChainStatusOut:
        return cls(
            ref=c.ref,
            section=c.section,
            paper_id=c.paper_id,
            state=c.state,
            can_generate=c.can_generate,
            reason=c.reason,
            detail=c.detail,
            recorded_version_id=c.recorded_version_id,
            recorded_version_label=c.recorded_version_label,
        )


class ReferenceChangesOut(BaseModel):
    """What regeneration did to the paper's references (E4): only references the Binder
    reliably owns are ever removed; everything else is kept, and a kept reference whose target
    the new block lacks is listed for a person's review."""

    added: list[str]
    removed: list[str]
    kept: list[str]
    for_review: list[str]


class RegenerationOut(BaseModel):
    references: ReferenceChangesOut
    previous_run_id: str | None
    run_id: str | None


class SpinePapersStatusOut(BaseModel):
    can_generate: bool
    reason: str | None
    version_id: uuid.UUID | None
    version_label: str | None
    version_hash: str | None
    areas: list[AreaStatusOut]
    chain: ChainStatusOut
    map_problems: list[str]
    unassigned_heads: list[str]
    # D38: where the areas come from: the template's own map, one derived from the Spine's
    # tree, or none; head groups the derivation could not give a letter D-T.
    map_source: str
    beyond_letters: list[str]

    @classmethod
    def build(cls, s: SpinePapersStatus) -> SpinePapersStatusOut:
        return cls(
            can_generate=s.can_generate,
            reason=s.reason,
            version_id=s.version_id,
            version_label=s.version_label,
            version_hash=s.version_hash,
            areas=[AreaStatusOut.build(a) for a in s.areas],
            chain=ChainStatusOut.build(s.chain),
            map_problems=list(s.map_problems),
            unassigned_heads=list(s.unassigned_heads),
            map_source=s.map_source,
            beyond_letters=list(s.beyond_letters),
        )
