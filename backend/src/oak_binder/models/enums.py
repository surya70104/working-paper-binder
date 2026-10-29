"""Fixed value sets from the specification. Stored as text with CHECK constraints, not as
PostgreSQL enum types, so a future value is one migration line, not a type rebuild."""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum


class Template(StrEnum):
    """Index template per engagement type (spec 3A)."""

    STATUTORY = "statutory"
    TAX_AUDIT = "tax_audit"
    BANK_BRANCH = "bank_branch"
    INTERNAL = "internal"


class BinderState(StrEnum):
    """Open until Assemble freezes the file (spec 3F); purged once retention has expired and
    the content has been destroyed (spec 3G)."""

    OPEN = "open"
    ASSEMBLED = "assembled"
    PURGED = "purged"


class EventKind(StrEnum):
    """Append-only record of what happened to a binder after it left ordinary editing."""

    ASSEMBLED = "assembled"
    AMENDED = "amended"
    PURGED = "purged"
    PRODUCED = "produced"


class WpStatus(StrEnum):
    """draft -> prepared -> in review -> reviewed -> signed off (spec 3B)."""

    DRAFT = "draft"
    PREPARED = "prepared"
    IN_REVIEW = "in_review"
    REVIEWED = "reviewed"
    SIGNED_OFF = "signed_off"


# Standard sections (spec 3A): A acceptance, B planning and risk, C materiality,
# D-T financial statement areas, W completion, X report and opinion, Z EQR.
SECTIONS: tuple[str, ...] = tuple("ABCDEFGHIJKLMNOPQRST") + ("W", "X", "Z")

SHA256_HEX_SQL = "~ '^[0-9a-f]{64}$'"


def sql_list(values: Iterable[str]) -> str:
    """Render values for an SQL IN (...) list."""
    return ", ".join(f"'{value}'" for value in values)
