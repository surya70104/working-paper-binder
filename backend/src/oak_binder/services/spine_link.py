"""The binder's link to a Financial Spine engagement and version (spec 3A "tying to the
Financial Spine"; D29).

One binder ties to one Spine engagement and, within it, one version. The link may be set,
changed or cleared while the binder is open, after the Spine has confirmed the ids; once the
binder is assembled it is frozen with the file, since the manifest records it and the
FS-line checks of Stage C depend on it. An unlocked version may be linked while the work
goes on, but assembly needs a locked one (``assembly.blockers``). Nothing from the Spine is
copied into the Binder's database: the ids are stored, the figures are read when needed.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from oak_binder.errors import Conflict, Invalid, NotFound, SpineUnavailable
from oak_binder.models import Binder
from oak_binder.services.binders import require_open
from oak_binder.services.spine_client import SpineClient, SpineEngagement, SpineVersion


def set_link(
    session: Session,
    client: SpineClient | None,
    binder: Binder,
    *,
    engagement_id: uuid.UUID | None,
    version_id: uuid.UUID | None,
) -> Binder:
    """Set, change or clear the link on an open binder, after checking with the Spine that
    the engagement exists and the version belongs to it. Clearing the engagement clears the
    version with it."""
    require_open(binder)
    if engagement_id is None:
        version_id = None
    if engagement_id is not None:
        if client is None:
            raise Conflict(
                "no Financial Spine is configured (OAK_SPINE_URL), so a binder cannot be linked"
            )
        client.engagement(engagement_id)  # NotFound names the Spine's answer
        if version_id is not None:
            version = client.version(version_id)
            if version.engagement_id != engagement_id:
                raise Invalid(
                    f"Spine version {version_id} belongs to engagement {version.engagement_id}, "
                    f"not {engagement_id}"
                )
    binder.spine_engagement_id = engagement_id
    binder.spine_version_id = version_id
    session.flush()
    return binder


@dataclass(frozen=True)
class LinkStatus:
    configured: bool
    engagement_id: uuid.UUID | None
    version_id: uuid.UUID | None
    reachable: bool
    reason: str | None
    engagement: SpineEngagement | None
    version: SpineVersion | None


def status(client: SpineClient | None, binder: Binder) -> LinkStatus:
    """The link as stored plus a live read of the Spine. A Spine that cannot be read makes
    ``reachable`` false with the reason; the binder stays usable."""
    engagement_id = binder.spine_engagement_id
    version_id = binder.spine_version_id
    if client is None:
        return LinkStatus(
            False,
            engagement_id,
            version_id,
            False,
            "no Financial Spine is configured (OAK_SPINE_URL)" if engagement_id else None,
            None,
            None,
        )
    if engagement_id is None:
        return LinkStatus(True, None, None, True, None, None, None)
    try:
        engagement = client.engagement(engagement_id)
        version = client.version(version_id) if version_id is not None else None
    except (SpineUnavailable, NotFound) as exc:
        return LinkStatus(True, engagement_id, version_id, False, str(exc), None, None)
    return LinkStatus(True, engagement_id, version_id, True, None, engagement, version)
