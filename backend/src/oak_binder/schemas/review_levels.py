"""The review chain of a paper (spec 3D; Stage F, D33): preparer, the configured levels in
order, sign-off; which are done, by whom, when and on which version."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from oak_binder.services.review_levels import ReviewChain, Step


class ReviewStepOut(BaseModel):
    level: str
    kind: str  # preparer | review | sign_off
    done: bool
    by: str | None
    at: datetime | None
    version: int | None

    @classmethod
    def build(cls, s: Step) -> ReviewStepOut:
        return cls(level=s.level, kind=s.kind, done=s.done, by=s.by, at=s.at, version=s.version)


class ReviewChainOut(BaseModel):
    configured: list[str]
    steps: list[ReviewStepOut]
    next_level: str | None
    pending_levels: list[str]
    frozen: bool

    @classmethod
    def build(cls, c: ReviewChain) -> ReviewChainOut:
        return cls(
            configured=list(c.configured),
            steps=[ReviewStepOut.build(s) for s in c.steps],
            next_level=c.next_level,
            pending_levels=list(c.pending_levels),
            frozen=c.frozen,
        )
