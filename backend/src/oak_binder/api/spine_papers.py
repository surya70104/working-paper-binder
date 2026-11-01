"""Papers the Financial Spine produces (spec 3A, 3C; Stage E, D32): the status of the lead
schedules per area, and the action that generates them from the linked, locked version."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request, status

from oak_binder.api.deps import CurrentUser, DbSession, Now, Spine
from oak_binder.api.papers import paper_out
from oak_binder.config import Settings
from oak_binder.schemas.papers import PaperOut
from oak_binder.schemas.spine_papers import (
    LeadSchedulesIn,
    ReferenceChangesOut,
    RegenerationOut,
    SpinePapersStatusOut,
)
from oak_binder.services import access, binders, papers, spine_papers

router = APIRouter(prefix="/api/binders/{binder_id}/spine-papers", tags=["spine papers"])
papers_router = APIRouter(prefix="/api/papers", tags=["spine papers"])


class RegeneratedPaperOut(PaperOut):
    """The regenerated paper with what happened to its references."""

    regeneration: RegenerationOut


@papers_router.post("/{paper_id}/regenerate")
def regenerate_paper(
    paper_id: uuid.UUID,
    request: Request,
    session: DbSession,
    user: CurrentUser,
    now: Now,
    spine: Spine,
) -> RegeneratedPaperOut:
    """Rebuild a Spine paper from the binder's linked, locked version (E4): the Spine's fields
    are rewritten, the paper returns to draft, a new provenance row is appended, and only the
    references the Binder reliably owns follow the new block. Open binders only (409 once
    assembled); a repeat on an unchanged version is refused as one paper per run."""
    paper = papers.get_paper(session, paper_id)
    binder = papers.binder_of(session, paper)
    settings: Settings = request.app.state.settings
    previous = papers.latest_generation(session, paper)
    done = spine_papers.regenerate(
        session, spine, binder, paper, user=user, now=now, max_bytes=settings.max_provenance_bytes
    )
    out = paper_out(session, paper.id, spine)
    return RegeneratedPaperOut(
        **out.model_dump(),
        regeneration=RegenerationOut(
            references=ReferenceChangesOut(**done.references.record()),
            previous_run_id=previous.run_id if previous else None,
            run_id=done.generation.run_id,
        ),
    )


@router.get("")
def spine_papers_status(
    binder_id: uuid.UUID, request: Request, session: DbSession, now: Now, spine: Spine
) -> SpinePapersStatusOut:
    binder = binders.get_binder(session, binder_id)
    access.record(session, binder, access.reader(request, binder), "Spine papers", now)
    return SpinePapersStatusOut.build(spine_papers.status(session, spine, binder))


@router.post("/lead-schedules", status_code=status.HTTP_201_CREATED)
def generate_lead_schedules(
    binder_id: uuid.UUID,
    body: LeadSchedulesIn,
    request: Request,
    session: DbSession,
    user: CurrentUser,
    now: Now,
    spine: Spine,
) -> list[PaperOut]:
    """One draft lead schedule per named area (or per mapped area without one), built from the
    Spine's answers and filed with its provenance; a person then prepares and the chain signs
    off. Any authenticated user may ask (Stage E decision 11)."""
    binder = binders.get_binder(session, binder_id)
    settings: Settings = request.app.state.settings
    papers = spine_papers.lead_schedules(
        session,
        spine,
        binder,
        body.areas,
        user=user,
        now=now,
        max_bytes=settings.max_provenance_bytes,
    )
    return [paper_out(session, paper.id, spine) for paper in papers]


@router.post("/adjustment-chain", status_code=status.HTTP_201_CREATED)
def generate_adjustment_chain(
    binder_id: uuid.UUID,
    request: Request,
    session: DbSession,
    user: CurrentUser,
    now: Now,
    spine: Spine,
) -> PaperOut:
    """The binder's one adjustment-chain paper, W-ADJ in section W (E3): every adjustment of
    the linked, locked version in every status and the uncorrected schedule as served, with a
    reference to each working paper an adjustment names by exact text."""
    binder = binders.get_binder(session, binder_id)
    settings: Settings = request.app.state.settings
    paper = spine_papers.adjustment_chain(
        session, spine, binder, user=user, now=now, max_bytes=settings.max_provenance_bytes
    )
    return paper_out(session, paper.id, spine)
