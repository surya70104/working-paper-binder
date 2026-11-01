"""Review levels, configurable per engagement (spec 3D; Pass 2 Stage F, D33).

The chain a paper goes through is always: the preparer (spec 3B's prepare step, recorded on
the prepared version), then the binder's configured review levels in order, then the sign-off
(spec 3D, 8.9). A binder with no configured levels keeps the Pass 1 chain: one review, then
sign-off. Each level review is an append-only row naming the prepared version it reviewed; the
paper stays ``in_review`` until the last configured level is done, then the ordinary
``reviewed`` version is written with that last reviewer.

The configuration may change while the binder is open and no level review has been recorded
for any of its papers; once one has, it is frozen for good, at the service and at the database
(migration 0009's trigger), so a chain can never lose a level under a paper mid-review. After
assembly the binder is frozen anyway (spec 3F).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from oak_binder.errors import Conflict, Invalid
from oak_binder.models import Binder, Wp, WpReview, WpVersion
from oak_binder.services.binders import require_open

PREPARER = "preparer"
SPEC_LEVELS: tuple[str, ...] = ("senior", "manager", "partner", "EQR")  # spec 3D's words
MAX_LEVELS = 10
MAX_LEVEL_LENGTH = 60


def levels_of(binder: Binder) -> tuple[str, ...]:
    return tuple(binder.review_levels or ())


def frozen(session: Session, binder: Binder) -> bool:
    """True once any level review exists for a paper of this binder."""
    return (
        session.scalar(
            select(WpReview.id)
            .join(Wp, Wp.id == WpReview.wp_id)
            .where(Wp.binder_id == binder.id)
            .limit(1)
        )
        is not None
    )


def validate_levels(levels: list[str] | None) -> list[str] | None:
    """The configured review levels, cleaned: non-blank, unique, at most MAX_LEVELS, and never
    'preparer', which is always level one by spec 3B and is not configurable."""
    if levels is None:
        return None
    cleaned: list[str] = []
    for raw in levels:
        if not isinstance(raw, str) or not raw.strip():
            raise Invalid("a review level is a non-blank name")
        name = raw.strip()
        if len(name) > MAX_LEVEL_LENGTH:
            raise Invalid(f"a review level name is at most {MAX_LEVEL_LENGTH} characters")
        if name.lower() == PREPARER:
            raise Invalid(
                "'preparer' is always the first level (spec 3B: a paper is prepared before it is "
                "reviewed) and is not configured; list the review levels that follow it"
            )
        if name.lower() in {c.lower() for c in cleaned}:
            raise Invalid(f"review level {name!r} is listed twice")
        cleaned.append(name)
    if len(cleaned) > MAX_LEVELS:
        raise Invalid(f"at most {MAX_LEVELS} review levels")
    return cleaned or None  # an empty list means: no configured levels (Pass 1 chain)


def set_levels(session: Session, binder: Binder, levels: list[str] | None) -> Binder:
    """Configure the review levels of an open binder before any level review exists."""
    require_open(binder)
    cleaned = validate_levels(levels)
    if cleaned == (list(binder.review_levels) if binder.review_levels else None):
        return binder
    if frozen(session, binder):
        raise Conflict(
            "the review levels are frozen: a level review has been recorded on a paper of this "
            "binder, and the chain the reviews were made under cannot change (spec 3D, 3F; D33)"
        )
    binder.review_levels = cleaned
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        if "frozen" in str(exc):
            raise Conflict(
                "the review levels are frozen: a level review has been recorded on a paper of "
                "this binder (database rule, migration 0009)"
            ) from exc
        raise
    return binder


# --- the chain of one paper --------------------------------------------------------------------


@dataclass(frozen=True)
class Step:
    level: str
    kind: str  # "preparer" | "review" | "sign_off"
    done: bool
    by: str | None = None
    at: datetime | None = None
    version: int | None = None


@dataclass(frozen=True)
class ReviewChain:
    configured: tuple[str, ...]
    steps: tuple[Step, ...]
    next_level: str | None  # the review level the next "review" action records, if any
    frozen: bool
    pending_levels: tuple[str, ...] = field(default_factory=tuple)


def reviews_of(session: Session, version: WpVersion) -> list[WpReview]:
    return list(
        session.scalars(
            select(WpReview)
            .where(WpReview.wp_version_id == version.id)
            .order_by(WpReview.reviewed_at, WpReview.id)
        ).all()
    )


def cycle_versions(versions: list[WpVersion], current: WpVersion | None) -> list[WpVersion]:
    """The versions of the current cycle: from the latest prepared (or amendment) version to the
    end. A cycle starts at a version with no reviewer."""
    if current is None:
        return []
    start = 0
    for i, v in enumerate(versions):
        if v.reviewed_by is None:
            start = i
    return versions[start:]


def chain(session: Session, binder: Binder, paper: Wp, versions: list[WpVersion]) -> ReviewChain:
    """Preparer, configured levels, sign-off: which are done for the current cycle, by whom and
    when, and which review level comes next."""
    configured = levels_of(binder)
    is_frozen = frozen(session, binder)
    current = versions[-1] if versions else None
    cycle = cycle_versions(versions, current)
    prepared = cycle[0] if cycle else None
    steps: list[Step] = [
        Step(
            PREPARER,
            "preparer",
            prepared is not None,
            prepared.prepared_by if prepared else None,
            prepared.prepared_at if prepared else None,
            prepared.version if prepared else None,
        )
    ]
    reviewed = next((v for v in cycle if v.reviewed_by is not None), None)
    signed = next((v for v in cycle if v.signed_off_by is not None), None)
    next_level: str | None = None
    pending: list[str] = []
    if configured:
        rows = {r.level: r for r in reviews_of(session, prepared)} if prepared else {}
        for level in configured:
            row = rows.get(level)
            steps.append(
                Step(
                    level,
                    "review",
                    row is not None,
                    row.reviewer if row else None,
                    row.reviewed_at if row else None,
                    prepared.version if (row and prepared) else None,
                )
            )
            if row is None:
                pending.append(level)
        next_level = pending[0] if pending else None
    else:
        steps.append(
            Step(
                "review",
                "review",
                reviewed is not None,
                reviewed.reviewed_by if reviewed else None,
                reviewed.reviewed_at if reviewed else None,
                reviewed.version if reviewed else None,
            )
        )
        next_level = None if reviewed else "review"
    steps.append(
        Step(
            "sign-off",
            "sign_off",
            signed is not None,
            signed.signed_off_by if signed else None,
            signed.signed_off_at if signed else None,
            signed.version if signed else None,
        )
    )
    return ReviewChain(configured, tuple(steps), next_level, is_frozen, tuple(pending))


def record_level_review(
    session: Session, binder: Binder, paper: Wp, prepared: WpVersion, user: str, now: datetime
) -> tuple[WpReview, bool]:
    """Record the next configured level's review of ``prepared`` by ``user``. Returns the row
    and whether every configured level is now done. Called only when levels are configured."""
    configured = levels_of(binder)
    done = {r.level for r in reviews_of(session, prepared)}
    pending = [level for level in configured if level not in done]
    if not pending:
        raise Conflict(
            f"every review level of paper {paper.ref} is already recorded for version "
            f"{prepared.version}"
        )
    row = WpReview(
        wp_id=paper.id,
        wp_version_id=prepared.id,
        level=pending[0],
        reviewer=user,
        reviewed_at=now,
    )
    session.add(row)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        if "uq_wp_review_version_level" in str(exc):
            raise Conflict(
                f"level {pending[0]!r} of paper {paper.ref} was reviewed by another request at "
                "the same time; reload and try again"
            ) from exc
        raise
    return row, len(pending) == 1


def reviews_for_paper(session: Session, paper: Wp) -> list[WpReview]:
    return list(
        session.scalars(
            select(WpReview)
            .where(WpReview.wp_id == paper.id)
            .order_by(WpReview.reviewed_at, WpReview.id)
        ).all()
    )


def version_numbers(session: Session, paper: Wp) -> dict[uuid.UUID, int]:
    return {
        v.id: v.version
        for v in session.scalars(select(WpVersion).where(WpVersion.wp_id == paper.id)).all()
    }
