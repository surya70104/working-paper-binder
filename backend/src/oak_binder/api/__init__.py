"""Routers: templates, binders, papers, attachments, assembly and retention, review notes,
cross-references."""

from fastapi import APIRouter

from oak_binder.api.assembly import router as assembly_router
from oak_binder.api.attachments import router as attachments_router
from oak_binder.api.binders import router as binders_router
from oak_binder.api.generated import router as generated_router
from oak_binder.api.papers import router as papers_router
from oak_binder.api.records import router as records_router
from oak_binder.api.review_notes import router as review_notes_router
from oak_binder.api.spine import router as spine_router
from oak_binder.api.spine_papers import papers_router as regenerate_router
from oak_binder.api.spine_papers import router as spine_papers_router
from oak_binder.api.templates import router as templates_router
from oak_binder.api.xrefs import router as xrefs_router

router = APIRouter()
router.include_router(templates_router)
router.include_router(binders_router)
router.include_router(papers_router)
router.include_router(attachments_router)
router.include_router(assembly_router)
router.include_router(review_notes_router)
router.include_router(xrefs_router)
router.include_router(records_router)
router.include_router(spine_router)
router.include_router(generated_router)
router.include_router(spine_papers_router)
router.include_router(regenerate_router)

__all__ = ["router"]
