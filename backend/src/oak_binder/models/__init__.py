"""Database tables (spec 4). Pass 1: binder, wp, wp_version, wp_attachment, binder_event
(assembly, amendment, purge and production records) and review_note.

Importing this package registers every table on ``Base.metadata``; Alembic's env.py relies
on that. Remaining Pass 2 tables (xref, discussion, departure) and the unassigned
access_log arrive with their features.
"""

from oak_binder.models.access import AccessLog
from oak_binder.models.binder import Binder
from oak_binder.models.enums import SECTIONS, BinderState, EventKind, Template, WpStatus
from oak_binder.models.event import BinderEvent
from oak_binder.models.review_note import NoteState, ReviewNote
from oak_binder.models.wp import Wp, WpAttachment, WpVersion
from oak_binder.models.xref import Direction, Xref

__all__ = [
    "SECTIONS",
    "AccessLog",
    "Binder",
    "BinderEvent",
    "BinderState",
    "Direction",
    "EventKind",
    "NoteState",
    "ReviewNote",
    "Template",
    "Wp",
    "WpAttachment",
    "WpStatus",
    "WpVersion",
    "Xref",
]
