"""A read-only client for the Financial Spine (spec 3A, 3C, 3E; Pass 2 Stage B, D29).

The Spine is a separate service (``oak_spine``, in its own repository and database). The
Binder reaches it over HTTP only, through ``OAK_SPINE_URL``, and never writes to it: every
method here is a GET, and the test double asserts no other verb is ever sent. Results are
small frozen records holding the fields the Binder uses; fields the Spine adds later are
ignored.

Errors are mapped once, here: a transport fault, a timeout, a 5xx or a 429 becomes
``SpineUnavailable`` (503); a 404 becomes ``NotFound`` carrying the Spine's own message; a
401 or 403 says the Spine refused the credential; any other 4xx becomes ``Invalid`` with the
Spine's message; a body that is not the expected JSON is "an unexpected answer". The optional
bearer credential (``OAK_SPINE_CREDENTIAL``) is sent when set and never appears in an error,
a log or a ``repr``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import httpx

from oak_binder.config import Settings
from oak_binder.errors import Invalid, NotFound, SpineUnavailable

TIMEOUT = httpx.Timeout(30.0, connect=10.0)


@dataclass(frozen=True)
class SpineEngagement:
    id: uuid.UUID
    entity_id: uuid.UUID | None
    financial_year_end: date | None
    label: str


@dataclass(frozen=True)
class SpineVersion:
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
    prior_version_id: uuid.UUID | None
    adjustments: dict[str, int] | None


@dataclass(frozen=True)
class SpineLine:
    """One financial-statement line of the Schedule III presentation. ``head_id`` is the
    Spine's stable identifier and is what a cross-reference names (Stage C); ``label`` is
    for display."""

    head_id: str
    label: str
    side: str | None
    depth: int | None
    item: str | None
    current: str | None
    prior: str | None
    has_figures: bool


@dataclass(frozen=True)
class SpinePresentation:
    version_id: uuid.UUID
    is_locked: bool
    provisional: bool
    status: str
    hash: str | None
    lines: tuple[SpineLine, ...]


@dataclass(frozen=True)
class SpineHead:
    """One head of the Spine's Schedule III tree (``GET /api/tree``). ``parent`` is the id of
    the head this one sits under, or None for a root, exactly as the Spine serves it: the
    Binder derives nothing from the shape of an id (Stage E, D32)."""

    id: str
    parent: str | None
    label: str
    side: str | None
    depth: int | None
    mappable: bool


@dataclass(frozen=True)
class SpineTree:
    division: str | None
    version: int | None
    heads: tuple[SpineHead, ...]

    def by_id(self) -> dict[str, SpineHead]:
        return {head.id: head for head in self.heads}


def _uuid(value: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value)) if value else None
    except ValueError:
        return None


def _time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def parse_version(raw: Any) -> SpineVersion:
    if not isinstance(raw, dict):
        raise SpineUnavailable("the Spine gave an unexpected answer for a version")
    version_id = _uuid(raw.get("version_id"))
    engagement_id = _uuid(raw.get("engagement_id"))
    if version_id is None or engagement_id is None:
        raise SpineUnavailable("the Spine gave an unexpected answer for a version")
    counts = raw.get("adjustments")
    return SpineVersion(
        version_id=version_id,
        engagement_id=engagement_id,
        version_no=int(raw["version_no"]) if raw.get("version_no") is not None else None,
        label=str(raw.get("label") or ""),
        is_locked=bool(raw.get("is_locked")),
        locked_by=raw.get("locked_by") or None,
        locked_at=_time(raw.get("locked_at")),
        hash=str(raw["hash"]) if raw.get("hash") else None,
        performance_materiality=(
            str(raw["performance_materiality"])
            if raw.get("performance_materiality") is not None
            else None
        ),
        pm_source=raw.get("pm_source") or None,
        prior_version_id=_uuid(raw.get("prior_version_id")),
        adjustments=(
            {str(k): int(v) for k, v in counts.items()} if isinstance(counts, dict) else None
        ),
    )


def parse_engagement(raw: Any) -> SpineEngagement:
    if not isinstance(raw, dict) or _uuid(raw.get("id")) is None:
        raise SpineUnavailable("the Spine gave an unexpected answer for an engagement")
    engagement_id = _uuid(raw.get("id"))
    assert engagement_id is not None  # noqa: S101
    return SpineEngagement(
        id=engagement_id,
        entity_id=_uuid(raw.get("entity_id")),
        financial_year_end=_date(raw.get("financial_year_end")),
        label=str(raw.get("label") or ""),
    )


def parse_presentation(raw: Any) -> SpinePresentation:
    if not isinstance(raw, dict) or _uuid(raw.get("version_id")) is None:
        raise SpineUnavailable("the Spine gave an unexpected answer for a presentation")
    version_id = _uuid(raw.get("version_id"))
    assert version_id is not None  # noqa: S101
    lines: list[SpineLine] = []
    for statement in ("balance_sheet", "profit_and_loss"):
        block = raw.get(statement)
        served = block.get("lines") if isinstance(block, dict) else None
        for entry in served if isinstance(served, list) else []:
            if not isinstance(entry, dict) or not entry.get("head_id"):
                continue  # computed subtotals carry "id", not a head
            lines.append(
                SpineLine(
                    head_id=str(entry["head_id"]),
                    label=str(entry.get("label") or entry["head_id"]),
                    side=entry.get("side"),
                    depth=int(entry["depth"]) if entry.get("depth") is not None else None,
                    item=entry.get("item"),
                    current=entry.get("current"),
                    prior=entry.get("prior"),
                    has_figures=bool(entry.get("has_figures")),
                )
            )
    return SpinePresentation(
        version_id=version_id,
        is_locked=bool(raw.get("is_locked")),
        provisional=bool(raw.get("provisional", not raw.get("is_locked"))),
        status=str(raw.get("status") or "unknown"),
        hash=str(raw["hash"]) if raw.get("hash") else None,
        lines=tuple(lines),
    )


def parse_tree(raw: Any) -> SpineTree:
    """The Schedule III tree as served: every head with its explicit parent. A head without
    an id is an unexpected answer; a parent naming no served head is kept as served (the
    area-map check reports it)."""
    if not isinstance(raw, dict) or not isinstance(raw.get("heads"), list):
        raise SpineUnavailable("the Spine gave an unexpected answer for the Schedule III tree")
    heads: list[SpineHead] = []
    for entry in raw["heads"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not entry["id"]:
            raise SpineUnavailable("the Spine gave an unexpected answer for the Schedule III tree")
        parent = entry.get("parent")
        heads.append(
            SpineHead(
                id=entry["id"],
                parent=str(parent) if isinstance(parent, str) and parent else None,
                label=str(entry.get("label") or entry["id"]),
                side=entry.get("side") if isinstance(entry.get("side"), str) else None,
                depth=int(entry["depth"]) if isinstance(entry.get("depth"), int) else None,
                mappable=bool(entry.get("mappable", False)),
            )
        )
    version = raw.get("version")
    return SpineTree(
        division=str(raw["division"]) if raw.get("division") is not None else None,
        version=int(version) if isinstance(version, int) else None,
        heads=tuple(heads),
    )


def _message(response: httpx.Response) -> str:
    try:
        detail = response.json().get("detail")
    except (ValueError, AttributeError):
        return response.reason_phrase or f"HTTP {response.status_code}"
    if isinstance(detail, dict):
        return str(detail.get("message") or detail.get("code") or detail)[:300]
    return str(detail)[:300]


class SpineClient:
    """GET-only access to one Spine. ``base_url`` is the service root (the ``/api`` prefix is
    added here), so a URL copied from the Spine's README works as it is."""

    def __init__(self, base_url: str, http: httpx.Client, credential: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self._http = http
        self._credential = (credential or "").strip() or None

    def __repr__(self) -> str:
        return f"SpineClient({self.base_url}, credential={'set' if self._credential else 'none'})"

    def _get(self, path: str, *, what: str, params: dict[str, str] | None = None) -> Any:
        headers = {"Accept": "application/json"}
        if self._credential:
            headers["Authorization"] = f"Bearer {self._credential}"
        url = f"{self.base_url}/api{path}"
        try:
            response = self._http.get(url, params=params, headers=headers, timeout=TIMEOUT)
        except httpx.TimeoutException:
            raise SpineUnavailable(f"the Financial Spine did not answer in time ({what})") from None
        except httpx.HTTPError as exc:
            raise SpineUnavailable(
                f"the Financial Spine is unreachable ({what}; {type(exc).__name__})"
            ) from None
        if response.status_code == 404:
            raise NotFound(f"the Financial Spine has no such record: {_message(response)}")
        if response.status_code in (401, 403):
            raise SpineUnavailable(
                f"the Financial Spine refused the Binder's credential ({what}; "
                f"HTTP {response.status_code}): check OAK_SPINE_CREDENTIAL"
            )
        if response.status_code == 429 or response.status_code >= 500:
            raise SpineUnavailable(
                f"the Financial Spine could not answer ({what}; HTTP {response.status_code}: "
                f"{_message(response)})"
            )
        if response.status_code >= 400:
            raise Invalid(f"the Financial Spine refused ({what}): {_message(response)}")
        try:
            return response.json()
        except ValueError:
            raise SpineUnavailable(
                f"the Financial Spine gave an unexpected answer ({what})"
            ) from None

    def tree(self) -> SpineTree:
        """The Schedule III head tree, the only source of parent–child relationships between
        heads (Stage E, D32)."""
        return parse_tree(self._get("/tree", what="the Schedule III tree"))

    def health(self) -> dict[str, Any]:
        body = self._get("/health", what="health check")
        return body if isinstance(body, dict) else {}

    def engagement(self, engagement_id: uuid.UUID) -> SpineEngagement:
        return parse_engagement(
            self._get(f"/engagements/{engagement_id}", what=f"engagement {engagement_id}")
        )

    def versions(self, engagement_id: uuid.UUID) -> list[SpineVersion]:
        body = self._get(
            f"/engagements/{engagement_id}/spine-versions",
            what=f"versions of engagement {engagement_id}",
        )
        if not isinstance(body, list):
            raise SpineUnavailable("the Spine gave an unexpected answer for a version list")
        return [parse_version(item) for item in body]

    def version(self, version_id: uuid.UUID) -> SpineVersion:
        return parse_version(
            self._get(f"/spine-versions/{version_id}", what=f"version {version_id}")
        )

    def presentation(self, version_id: uuid.UUID) -> SpinePresentation:
        return parse_presentation(
            self._get(
                f"/spine-versions/{version_id}/presentation",
                what=f"presentation of version {version_id}",
            )
        )

    def balances(self, version_id: uuid.UUID) -> dict[str, Any]:
        body = self._get(f"/spine-versions/{version_id}/balances", what=f"balances of {version_id}")
        if not isinstance(body, dict):
            raise SpineUnavailable("the Spine gave an unexpected answer for balances")
        return body

    def adjustments(self, version_id: uuid.UUID, status: str | None = None) -> list[dict[str, Any]]:
        body = self._get(
            f"/spine-versions/{version_id}/adjustments",
            what=f"adjustments of {version_id}",
            params={"status": status} if status else None,
        )
        if not isinstance(body, list):
            raise SpineUnavailable("the Spine gave an unexpected answer for adjustments")
        return [item for item in body if isinstance(item, dict)]

    def uncorrected(self, version_id: uuid.UUID) -> dict[str, Any]:
        body = self._get(
            f"/spine-versions/{version_id}/uncorrected", what=f"uncorrected of {version_id}"
        )
        if not isinstance(body, dict):
            raise SpineUnavailable("the Spine gave an unexpected answer for uncorrected")
        return body


def build_spine_client(settings: Settings, http: httpx.Client | None = None) -> SpineClient | None:
    """The client OAK_SPINE_URL configures, or None when no Spine is configured: every
    Spine-dependent feature then says so instead of failing."""
    if not settings.spine_url:
        return None
    return SpineClient(
        settings.spine_url, http or httpx.Client(timeout=TIMEOUT), settings.spine_credential
    )
