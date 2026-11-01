"""Read-only client for WorkMind run verification (spec 3C "one paper per accepted run";
Pass 2 completion work, D37).

WorkMind delivers a paper through the generated-paper intake like every other module. What
the intake must verify before filing it is that the run it names is an *accepted* run, and
WorkMind is the only authority on that. This client reads one record, ``GET
{OAK_WORKMIND_URL}/api/runs/{run_id}``, and reports the run's status and who accepted it when.
Nothing is written to WorkMind; nothing in the Binder depends on it being up except the
intake of a WorkMind paper, which says so when it is not.

The contract this client expects, kept to the fields the specification names and the fact the
intake needs, is the Binder's statement of what a WorkMind must serve (the module does not
exist yet; ``tests/fake_workmind.py`` is the local double it is tested against):

    {"run_id": "…", "status": "accepted" | "proposed" | "refused" | …,
     "accepted_by": "…" | null, "accepted_at": "<ISO 8601>" | null}

Any other top-level field is ignored. A missing or malformed record is an unexpected answer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from oak_binder.config import Settings
from oak_binder.errors import NotFound, WorkMindUnavailable

TIMEOUT = httpx.Timeout(10.0, connect=5.0)
ACCEPTED = "accepted"


@dataclass(frozen=True)
class WorkMindRun:
    run_id: str
    status: str
    accepted_by: str | None
    accepted_at: str | None
    endpoint: str

    @property
    def accepted(self) -> bool:
        return self.status == ACCEPTED


def _message(response: httpx.Response) -> str:
    try:
        detail = response.json().get("detail")
    except (ValueError, AttributeError):
        return response.text[:200]
    if isinstance(detail, dict):
        return str(detail.get("message") or detail)
    return str(detail) if detail else response.text[:200]


def parse_run(raw: Any, run_id: str, endpoint: str) -> WorkMindRun:
    if not isinstance(raw, dict) or not isinstance(raw.get("status"), str) or not raw["status"]:
        raise WorkMindUnavailable(f"WorkMind gave an unexpected answer for run {run_id!r}")
    served_id = raw.get("run_id")
    if served_id is not None and str(served_id) != run_id:
        raise WorkMindUnavailable(
            f"WorkMind answered for run {served_id!r} when run {run_id!r} was asked for"
        )
    accepted_by = raw.get("accepted_by")
    accepted_at = raw.get("accepted_at")
    return WorkMindRun(
        run_id=run_id,
        status=str(raw["status"]).strip(),
        accepted_by=str(accepted_by) if accepted_by else None,
        accepted_at=str(accepted_at) if accepted_at else None,
        endpoint=endpoint,
    )


class WorkMindClient:
    """GET only. Transport failures, timeouts and 5xx become WorkMindUnavailable (503); an
    unknown run is NotFound (404); a refused credential is WorkMindUnavailable, named."""

    def __init__(self, base_url: str, http: httpx.Client, credential: str | None = None) -> None:
        self._base = base_url.rstrip("/")
        self._http = http
        self._credential = credential

    def run(self, run_id: str) -> WorkMindRun:
        path = f"/api/runs/{run_id}"
        headers = {"Accept": "application/json"}
        if self._credential:
            headers["Authorization"] = f"Bearer {self._credential}"
        try:
            response = self._http.get(self._base + path, headers=headers)
        except httpx.TimeoutException as exc:
            raise WorkMindUnavailable(
                f"WorkMind did not answer in time for run {run_id!r}; the paper is not filed"
            ) from exc
        except httpx.HTTPError as exc:
            raise WorkMindUnavailable(
                f"WorkMind could not be reached ({type(exc).__name__}); the paper is not filed"
            ) from exc
        if response.status_code == 404:
            raise NotFound(f"WorkMind has no run {run_id!r}: {_message(response)}")
        if response.status_code in (401, 403):
            raise WorkMindUnavailable(
                "WorkMind refused the Binder's credential (OAK_WORKMIND_CREDENTIAL): "
                f"{_message(response)}"
            )
        if response.status_code >= 400:
            raise WorkMindUnavailable(
                f"WorkMind answered HTTP {response.status_code} for run {run_id!r}: "
                f"{_message(response)}"
            )
        try:
            raw = response.json()
        except ValueError as exc:
            raise WorkMindUnavailable(
                f"WorkMind gave an unexpected answer for run {run_id!r} (not JSON)"
            ) from exc
        return parse_run(raw, run_id, path)


def build_workmind_client(
    settings: Settings, http: httpx.Client | None = None
) -> WorkMindClient | None:
    """The client OAK_WORKMIND_URL configures, or None when no WorkMind is configured: the
    intake of a WorkMind paper then says so (503) instead of filing an unverified run."""
    if not settings.workmind_url:
        return None
    return WorkMindClient(
        settings.workmind_url, http or httpx.Client(timeout=TIMEOUT), settings.workmind_credential
    )
