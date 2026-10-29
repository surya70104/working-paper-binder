from __future__ import annotations

from fastapi import APIRouter

from oak_binder.schemas.templates import TemplateOut
from oak_binder.services.templates import list_templates, load_template

router = APIRouter(prefix="/api/templates", tags=["templates"])


@router.get("")
def get_templates() -> list[TemplateOut]:
    return [TemplateOut.from_template(t) for t in list_templates()]


@router.get("/{name}")
def get_template(name: str) -> TemplateOut:
    return TemplateOut.from_template(load_template(name))
