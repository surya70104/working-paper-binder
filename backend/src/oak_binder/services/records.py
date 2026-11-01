"""The discussions and departures logs (spec 2, 3H, 4; D28).

Entries are recorded, never edited or deleted. While the binder is open an entry is ordinary
work. After assembly an entry is new evidence added to a frozen file, so it follows the
spec's post-assembly rule (3F, 8.4): it needs a reason, an ``amended`` event records the
author, date and reason, and the logs are part of the manifest, so the file no longer
matches its recorded hash until it is re-assembled, which production requires. A purged
binder takes no entries.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from oak_binder.errors import Conflict, Invalid
from oak_binder.models import Binder, BinderState, Departure, Discussion, EventKind
from oak_binder.services.assembly import record as record_event
from oak_binder.services.assembly import require_reason

MAX_PARTICIPANTS = 50


def _clean(value: str | None, name: str, *, required: bool) -> str | None:
    text = (value or "").strip()
    if not text:
        if required:
            raise Invalid(f"{name} must not be blank")
        return None
    return text


def _gate(binder: Binder, amendment_reason: str | None) -> str | None:
    """What the binder's state demands of a new entry: nothing while open, a reason once
    assembled, refusal once purged. Returns the reason to record, if any."""
    if binder.state == BinderState.PURGED:
        raise Conflict(
            f"binder for {binder.engagement!r} was purged after retention; "
            "its content is gone and nothing can be recorded"
        )
    if binder.state == BinderState.ASSEMBLED:
        return require_reason(amendment_reason)
    if amendment_reason is not None:
        raise Invalid(
            "amendment_reason applies to an assembled binder only; this binder is open, so "
            "record the entry directly"
        )
    return None


def _participants(raw: list[str]) -> list[str]:
    cleaned = [p.strip() for p in raw if p and p.strip()]
    if not cleaned:
        raise Invalid("a discussion names at least one participant")
    if len(cleaned) > MAX_PARTICIPANTS:
        raise Invalid(f"a discussion names at most {MAX_PARTICIPANTS} participants")
    return cleaned


def record_discussion(
    session: Session,
    binder: Binder,
    *,
    date: date,
    participants: list[str],
    matter: str,
    outcome: str | None,
    amendment_reason: str | None,
    user: str,
    now: datetime,
) -> Discussion:
    reason = _gate(binder, amendment_reason)
    row = Discussion(
        binder_id=binder.id,
        date=date,
        participants=_participants(participants),
        matter=_clean(matter, "matter", required=True) or "",
        outcome=_clean(outcome, "outcome", required=False),
        recorded_by=user,
        recorded_at=now,
    )
    session.add(row)
    session.flush()
    if reason is not None:
        record_event(
            session,
            binder,
            EventKind.AMENDED,
            user,
            now,
            reason=reason,
            details={
                "record": "discussion",
                "discussion_id": str(row.id),
                "date": date.isoformat(),
            },
        )
    return row


def record_departure(
    session: Session,
    binder: Binder,
    *,
    requirement: str,
    reason: str,
    alternative_procedure: str,
    approved_by: str | None,
    amendment_reason: str | None,
    user: str,
    now: datetime,
) -> Departure:
    why = _gate(binder, amendment_reason)
    row = Departure(
        binder_id=binder.id,
        requirement=_clean(requirement, "requirement", required=True) or "",
        reason=_clean(reason, "reason", required=True) or "",
        alternative_procedure=_clean(alternative_procedure, "alternative_procedure", required=True)
        or "",
        approved_by=_clean(approved_by, "approved_by", required=False),
        recorded_by=user,
        recorded_at=now,
    )
    session.add(row)
    session.flush()
    if why is not None:
        record_event(
            session,
            binder,
            EventKind.AMENDED,
            user,
            now,
            reason=why,
            details={"record": "departure", "departure_id": str(row.id)},
        )
    return row


def discussions(session: Session, binder: Binder) -> list[Discussion]:
    return list(
        session.scalars(
            select(Discussion)
            .where(Discussion.binder_id == binder.id)
            .order_by(Discussion.date, Discussion.recorded_at, Discussion.id)
        ).all()
    )


def departures(session: Session, binder: Binder) -> list[Departure]:
    return list(
        session.scalars(
            select(Departure)
            .where(Departure.binder_id == binder.id)
            .order_by(Departure.recorded_at, Departure.id)
        ).all()
    )
