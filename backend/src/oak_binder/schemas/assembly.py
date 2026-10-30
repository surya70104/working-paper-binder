from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from oak_binder.clocks import days_to_assembly
from oak_binder.models import Binder, BinderEvent
from oak_binder.services.assembly import Blocker, Verification


class BlockerOut(BaseModel):
    kind: str
    ref: str | None
    detail: str


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: Any
    kind: str
    actor: str
    at: datetime
    reason: str | None
    details: dict[str, Any]


class AssemblyStatusOut(BaseModel):
    state: str
    report_date: date | None
    assembly_due: date | None
    days_to_assembly: int | None
    assembled_at: datetime | None
    assembly_hash: str | None
    retention_until: date | None
    purge_allowed: bool
    # False between an amendment and the next re-assembly: the recorded manifest no longer
    # describes the file, so production is refused until it is re-assembled.
    matches_recorded_manifest: bool
    blockers: list[BlockerOut]
    not_checked: list[str]
    manifest: dict[str, Any] | None
    events: list[EventOut]

    @classmethod
    def build(
        cls,
        binder: Binder,
        found: list[Blocker],
        not_checked: tuple[str, ...],
        manifest: dict[str, Any] | None,
        history: list[BinderEvent],
        today: date,
        matches_recorded_manifest: bool,
    ) -> AssemblyStatusOut:
        return cls(
            matches_recorded_manifest=matches_recorded_manifest,
            state=binder.state,
            report_date=binder.report_date,
            assembly_due=binder.assembly_due,
            days_to_assembly=(
                days_to_assembly(binder.assembly_due, today) if binder.assembly_due else None
            ),
            assembled_at=binder.assembled_at,
            assembly_hash=binder.assembly_hash,
            retention_until=binder.retention_until,
            purge_allowed=(
                binder.state == "assembled"
                and binder.retention_until is not None
                and today >= binder.retention_until
            ),
            blockers=[BlockerOut(kind=b.kind, ref=b.ref, detail=b.detail) for b in found],
            not_checked=list(not_checked),
            manifest=manifest,
            events=[
                EventOut(
                    id=str(e.id),
                    kind=e.kind,
                    actor=e.actor,
                    at=e.at,
                    reason=e.reason,
                    # The manifest is large; it is served in its own field above.
                    details={k: v for k, v in e.details.items() if k != "manifest"},
                )
                for e in history
            ],
        )


class CheckOut(BaseModel):
    item: str
    ok: bool
    detail: str


class VerificationOut(BaseModel):
    ok: bool
    assembly_hash: str | None
    recomputed_from_recorded_manifest: str | None
    current_file_hash: str
    current_matches_assembled: bool
    checks: list[CheckOut]

    @classmethod
    def build(cls, v: Verification) -> VerificationOut:
        return cls(
            ok=v.ok,
            assembly_hash=v.assembly_hash,
            recomputed_from_recorded_manifest=v.recomputed_from_recorded_manifest,
            current_file_hash=v.current_file_hash,
            current_matches_assembled=v.current_matches_assembled,
            checks=[CheckOut(item=c.item, ok=c.ok, detail=c.detail) for c in v.checks],
        )
