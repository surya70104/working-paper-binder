from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from oak_binder.services.spine_client import SpineEngagement, SpineVersion
from oak_binder.services.spine_link import LinkStatus


class SpineEngagementOut(BaseModel):
    id: uuid.UUID
    entity_id: uuid.UUID | None
    financial_year_end: date | None
    label: str

    @classmethod
    def build(cls, e: SpineEngagement) -> SpineEngagementOut:
        return cls(
            id=e.id, entity_id=e.entity_id, financial_year_end=e.financial_year_end, label=e.label
        )


class SpineVersionOut(BaseModel):
    version_id: uuid.UUID
    engagement_id: uuid.UUID
    version_no: int | None
    label: str
    is_locked: bool
    locked_by: str | None
    locked_at: datetime | None
    hash: str | None
    performance_materiality: str | None
    pm_source: str | None
    adjustments: dict[str, int] | None

    @classmethod
    def build(cls, v: SpineVersion) -> SpineVersionOut:
        return cls(
            version_id=v.version_id,
            engagement_id=v.engagement_id,
            version_no=v.version_no,
            label=v.label,
            is_locked=v.is_locked,
            locked_by=v.locked_by,
            locked_at=v.locked_at,
            hash=v.hash,
            performance_materiality=v.performance_materiality,
            pm_source=v.pm_source,
            adjustments=v.adjustments,
        )


class SpineLinkOut(BaseModel):
    """The binder's link and what the Spine says about it right now."""

    configured: bool
    engagement_id: uuid.UUID | None
    version_id: uuid.UUID | None
    reachable: bool
    reason: str | None
    engagement: SpineEngagementOut | None
    version: SpineVersionOut | None

    @classmethod
    def build(cls, s: LinkStatus) -> SpineLinkOut:
        return cls(
            configured=s.configured,
            engagement_id=s.engagement_id,
            version_id=s.version_id,
            reachable=s.reachable,
            reason=s.reason,
            engagement=SpineEngagementOut.build(s.engagement) if s.engagement else None,
            version=SpineVersionOut.build(s.version) if s.version else None,
        )
