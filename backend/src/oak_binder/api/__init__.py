"""Routers: templates, binders, papers, attachments, assembly and retention."""

from fastapi import APIRouter

from oak_binder.api.assembly import router as assembly_router
from oak_binder.api.attachments import router as attachments_router
from oak_binder.api.binders import router as binders_router
from oak_binder.api.papers import router as papers_router
from oak_binder.api.review_notes import router as review_notes_router
from oak_binder.api.templates import router as templates_router

router = APIRouter()
router.include_router(templates_router)
router.include_router(binders_router)
router.include_router(papers_router)
router.include_router(attachments_router)
router.include_router(assembly_router)
router.include_router(review_notes_router)

__all__ = ["router"]
