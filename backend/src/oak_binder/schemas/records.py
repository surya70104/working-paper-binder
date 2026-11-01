from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class DiscussionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    # Names with a role after each, for example "R. Mehta (TCWG, Audit Committee Chair)".
    participants: list[str] = Field(min_length=1, max_length=50)
    matter: str
    outcome: str | None = None
    # Required once the binder is assembled (spec 3F); refused while it is open.
    amendment_reason: str | None = None


class DiscussionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    binder_id: uuid.UUID
    date: date
    participants: list[str]
    matter: str
    outcome: str | None
    recorded_by: str
    recorded_at: datetime


class DepartureIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement: str
    reason: str
    alternative_procedure: str
    approved_by: str | None = None
    amendment_reason: str | None = None


class DepartureOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    binder_id: uuid.UUID
    requirement: str
    reason: str
    alternative_procedure: str
    approved_by: str | None
    recorded_by: str
    recorded_at: datetime
