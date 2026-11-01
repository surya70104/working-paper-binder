"""The financial-statement lines a binder's references can name (spec 3E; Pass 2 Stage C,
D30): the Schedule III presentation lines of the linked Spine version, keyed by the Spine's
stable ``head_id``.

Lines are available only when the binder is linked to a Spine version and the Spine can be
read. Without them a reference to an FS line is free text and *not checked*; with them it
must name a line, and one that does not is broken and blocks assembly.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from oak_binder.errors import NotFound, SpineUnavailable
from oak_binder.models import Binder
from oak_binder.services.spine_client import SpineClient, SpineLine


@dataclass(frozen=True)
class FsLines:
    available: bool
    reason: str | None
    version_locked: bool
    lines: dict[str, SpineLine] = field(default_factory=dict)

    def label(self, head_id: str) -> str | None:
        line = self.lines.get(head_id)
        return line.label if line else None


UNLINKED = FsLines(False, "the binder is not linked to a Financial Spine version", False)


def for_binder(client: SpineClient | None, binder: Binder) -> FsLines:
    """The lines of the linked version, or why there are none."""
    if binder.spine_version_id is None:
        return UNLINKED
    if client is None:
        return FsLines(False, "no Financial Spine is configured (OAK_SPINE_URL)", False)
    try:
        presentation = client.presentation(binder.spine_version_id)
    except (SpineUnavailable, NotFound) as exc:
        return FsLines(False, str(exc), False)
    if presentation.status != "ready":
        return FsLines(
            False,
            f"the linked Spine version's statements are {presentation.status}; "
            "its lines cannot be read until it is ready",
            presentation.is_locked,
        )
    return FsLines(
        True, None, presentation.is_locked, {line.head_id: line for line in presentation.lines}
    )


# --- the lines as verified at assembly (D30 follow-up) ---------------------------------------
#
# Assembly verifies every FS-line reference against the lines read at that moment. Those
# lines are recorded with the assembled event, so that producing the file later does not
# depend on the Spine answering again: the archive states what was verified, as it was
# verified. Binders assembled before this was recorded carry no such record and fall back to
# reading the Spine, as before.

RECORD_VERSION = 1


def to_record(lines: FsLines, version_id: Any) -> dict[str, Any]:
    """The available lines as JSON for the assembled event's details."""
    assert lines.available  # noqa: S101
    return {
        "record_version": RECORD_VERSION,
        "version_id": str(version_id),
        "version_locked": lines.version_locked,
        "lines": [asdict(line) for line in lines.lines.values()],
    }


def from_record(record: Any) -> FsLines | None:
    """The lines an assembled event recorded, or None when it recorded none (a binder
    assembled before the record existed, or one whose lines were not available)."""
    if not isinstance(record, dict) or not isinstance(record.get("lines"), list):
        return None
    lines: dict[str, SpineLine] = {}
    for item in record["lines"]:
        if not isinstance(item, dict) or not isinstance(item.get("head_id"), str):
            return None
        line = SpineLine(
            head_id=item["head_id"],
            label=str(item.get("label") or item["head_id"]),
            side=item.get("side"),
            depth=item.get("depth"),
            item=item.get("item"),
            current=item.get("current"),
            prior=item.get("prior"),
            has_figures=bool(item.get("has_figures", False)),
        )
        lines[line.head_id] = line
    return FsLines(True, None, bool(record.get("version_locked", False)), lines)
