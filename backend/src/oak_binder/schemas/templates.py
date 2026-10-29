from __future__ import annotations

from pydantic import BaseModel

from oak_binder.services.templates import IndexTemplate


class SectionOut(BaseModel):
    code: str
    name: str


class RequiredPaperOut(BaseModel):
    ref: str
    section: str
    title: str
    sa_refs: list[str]


class TemplateOut(BaseModel):
    name: str
    label: str
    status: str
    draft: bool
    placeholders: list[str]
    sections: list[SectionOut]
    required: list[RequiredPaperOut]

    @classmethod
    def from_template(cls, template: IndexTemplate) -> TemplateOut:
        return cls(
            name=template.name,
            label=template.label,
            status=template.status,
            draft=template.draft,
            placeholders=template.placeholders(),
            sections=[SectionOut(code=s.code, name=s.name) for s in template.sections],
            required=[
                RequiredPaperOut(
                    ref=r.ref, section=r.section, title=r.title, sa_refs=list(r.sa_refs)
                )
                for r in template.required
            ],
        )
