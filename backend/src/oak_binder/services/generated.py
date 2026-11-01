"""Generated-paper intake (spec 3C, 7, 8.8; Pass 2 Stage D, D31).

A module delivers a complete paper with its inputs and citations. The Binder checks what the
specification names for the source, refuses what it cannot accept, writes the paper as an
ordinary draft (decision 1: a person prepares and the chain signs off) and records the
provenance in the append-only ``wp_generation`` table (decision 2). Every later version body
embeds that record, so the content hash covers the inputs and citations and the archive
carries them. The module's fields are then locked (decision 3): the paper is not retyped here.

Per-source rules, from the spec's words and nothing else:

- materiality: benchmark, band and Spine figures present; the figures' version must be the
  binder's linked Spine version when there is one, else they are kept and marked not checked
  (decision 5);
- sampling: formula and seed present, and both printed on the paper, that is, found verbatim
  in its text (spec 3C, 8.8; decision 4);
- analytical_review: current and prior periods and the thresholds present;
- workmind: the contract is validated in full, a conclusion is refused (spec 7: not drafted
  automatically), then intake is refused until the module exists and an accepted run can be
  verified (decision 6);
- spine: Stage E.

A run id is required for WorkMind, optional otherwise, and unique within its source when
given (decision 7). Intake after assembly is refused (decision 9). Supporting attachments are
uploaded separately through the existing attachment API after intake creates the draft paper,
but before the preparer completes preparation; the preparer reviews the generated content and
its supporting attachments together before proceeding (decision 10; an attachment row belongs
to its paper, D17, so nothing can attach before the paper exists).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from oak_binder.errors import Conflict, Invalid, NotAvailable, TooLarge
from oak_binder.hashing import canonical_json, content_hash
from oak_binder.models import Binder, Wp, WpGeneration, WpStatus
from oak_binder.models.generation import locked_fields_for
from oak_binder.schemas.generated import GeneratedPaperIn
from oak_binder.services import papers as paper_service
from oak_binder.services.binders import require_open


def locked_hash(paper: Wp, source: str) -> str:
    """The content hash of the module's fields, recorded at intake so that any later change
    to them is detectable against every version body."""
    return content_hash(
        {
            name: list(paper.sa_refs) if name == "sa_refs" else getattr(paper, name)
            for name in locked_fields_for(source)
        }
    )


def _paper_text(fields: dict[str, Any]) -> str:
    return "\n".join(
        str(fields[name])
        for name in ("title", "objective", "procedure", "population_sample", "result", "conclusion")
        if fields.get(name)
    )


def _check_sampling(payload: GeneratedPaperIn) -> None:
    block = payload.generated.sampling
    assert block is not None  # noqa: S101
    text = _paper_text(payload.paper.model_dump())
    for name, value in (("formula", block.formula), ("seed", str(block.seed))):
        if value not in text:
            raise Invalid(
                f"a sampling paper carries its {name} printed on it (spec 3C, 8.8): "
                f"{value!r} does not appear in the paper's text"
            )


def _check_materiality(payload: GeneratedPaperIn, binder: Binder) -> str:
    block = payload.generated.materiality
    assert block is not None  # noqa: S101
    offered = block.spine_figures.version_id
    if binder.spine_version_id is None:
        return "not_checked"
    if offered != binder.spine_version_id:
        raise Invalid(
            f"the memo's figures come from Spine version {offered}, but this binder is linked "
            f"to version {binder.spine_version_id} (D29); regenerate the memo from the linked "
            "version"
        )
    return "verified"


def _check_run(session: Session, source: str, run_id: str | None) -> None:
    if run_id is None:
        return
    existing = session.scalar(
        select(WpGeneration)
        .where(WpGeneration.source == source, WpGeneration.run_id == run_id)
        .limit(1)
    )
    if existing is not None:
        paper = session.get(Wp, existing.wp_id)
        where = f" as paper {paper.ref}" if paper else ""
        raise Conflict(
            f"run {run_id!r} of {source} was already received{where}: one paper per run (spec 3C)"
        )


def receive(
    session: Session,
    binder: Binder,
    payload: GeneratedPaperIn,
    *,
    user: str,
    now: datetime,
    max_bytes: int,
    allow_spine: bool = False,
) -> Wp:
    """Validate the delivery for its source, write the draft paper and its provenance row.
    Raises Invalid (422), Conflict (409), TooLarge (413) or NotAvailable (501).

    ``allow_spine`` is set only by ``services.spine_papers``, which builds a Spine paper from
    the linked version itself (Stage E, D32); the HTTP intake never sets it."""
    require_open(binder)
    generated = payload.generated
    block = generated.model_dump(mode="json")
    size = len(canonical_json(block).encode("utf-8"))
    if size > max_bytes:
        raise TooLarge(
            f"the provenance block is {size} bytes; the limit is {max_bytes} "
            "(OAK_MAX_PROVENANCE_BYTES)"
        )
    if generated.source == "spine" and not allow_spine:
        # Stage E: lead schedules and the adjustment chain are built by the Binder itself from
        # the linked Spine version, through the Spine-papers action; no outside caller can
        # deliver a Spine paper through this endpoint (D32).
        raise Invalid(
            "Spine-produced papers (lead schedules, the adjustment chain) arrive through the "
            "Binder's own Spine-papers action, not this endpoint (Stage E, D32)"
        )
    if generated.source == "workmind":
        if payload.paper.conclusion is not None:
            raise Invalid(
                "a WorkMind paper arrives without a conclusion: conclusions are not drafted "
                "automatically (spec 7); a person writes it"
            )
        raise NotAvailable(
            "WorkMind intake is not available yet: the module does not exist and an accepted "
            "run cannot be verified (decision 6, D31). The delivery itself is valid under the "
            "contract."
        )
    spine_check: str | None = None
    if generated.source == "materiality":
        spine_check = _check_materiality(payload, binder)
    elif generated.source == "sampling":
        _check_sampling(payload)
    _check_run(session, generated.source, generated.run_id)

    paper = paper_service.create_paper(session, binder, payload.paper.model_dump())
    row = WpGeneration(
        wp_id=paper.id,
        source=generated.source,
        module=generated.module,
        module_version=generated.module_version,
        run_id=generated.run_id,
        generated_at=generated.generated_at,
        received_by=user,
        received_at=now,
        payload=block,
        content_hash_at_intake=locked_hash(paper, generated.source),
        spine_figures=spine_check,
    )
    session.add(row)
    session.flush()
    return paper


def regenerate(
    session: Session,
    paper: Wp,
    payload: GeneratedPaperIn,
    *,
    user: str,
    now: datetime,
    max_bytes: int,
) -> WpGeneration:
    """Rewrite a Spine paper from a fresh Spine answer (Stage E step E4, D32): the Spine's
    fields are replaced, the paper returns to draft, and a new provenance row is appended.
    The person's objective, procedure and conclusion are kept; every earlier version stays.
    Only ``services.spine_papers`` calls this; a repeat on an unchanged version is refused as
    one paper per run."""
    binder = session.get(Binder, paper.binder_id)
    assert binder is not None  # noqa: S101
    require_open(binder)
    generated = payload.generated
    if generated.source != "spine":
        raise Invalid("only papers the Financial Spine produced are regenerated")
    previous = paper_service.latest_generation(session, paper)
    if previous is None or previous.source != "spine":
        raise Invalid(f"paper {paper.ref} was not generated from the Financial Spine")
    if payload.paper.ref != paper.ref:
        raise Invalid("the reference is stable and cannot be changed (spec 3B)")
    block = generated.model_dump(mode="json")
    size = len(canonical_json(block).encode("utf-8"))
    if size > max_bytes:
        raise TooLarge(
            f"the provenance block is {size} bytes; the limit is {max_bytes} "
            "(OAK_MAX_PROVENANCE_BYTES)"
        )
    _check_run(session, generated.source, generated.run_id)
    fields = payload.paper.model_dump()
    changes = {name: fields[name] for name in locked_fields_for("spine")}
    paper_service.apply_changes(paper, paper_service.validate_content(changes))
    paper.status = WpStatus.DRAFT
    session.flush()
    row = WpGeneration(
        wp_id=paper.id,
        source=generated.source,
        module=generated.module,
        module_version=generated.module_version,
        run_id=generated.run_id,
        generated_at=generated.generated_at,
        received_by=user,
        received_at=now,
        payload=block,
        content_hash_at_intake=locked_hash(paper, generated.source),
        spine_figures=None,
    )
    session.add(row)
    session.flush()
    return row


def for_binder(session: Session, binder: Binder) -> dict[Any, str]:
    """Paper id → source, for the index (which papers were generated)."""
    rows = session.execute(
        select(WpGeneration.wp_id, WpGeneration.source)
        .join(Wp, Wp.id == WpGeneration.wp_id)
        .where(Wp.binder_id == binder.id)
        .order_by(WpGeneration.received_at, WpGeneration.id)
    ).all()
    return {wp_id: source for wp_id, source in rows}
