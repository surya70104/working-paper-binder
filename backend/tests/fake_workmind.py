"""A WorkMind double for the tests (completion work, D37): an in-process HTTP transport that answers
``GET /api/runs/{run_id}`` with the record the Binder's client expects. It is the local,
controlled stand-in for a module that does not exist yet; nothing here is a live integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from oak_binder.services.workmind_client import WorkMindClient

BASE = "http://workmind.test"
TOKEN = "workmind-test-credential"  # noqa: S105
ACCEPTED_RUN = "wm-run-example-7f3a"  # the run the workmind.json fixture names
PROPOSED_RUN = "wm-run-proposed-0b11"
REFUSED_RUN = "wm-run-refused-9c42"


@dataclass(frozen=True)
class Call:
    method: str
    path: str
    headers: dict[str, str]


class FakeWorkMind:
    def __init__(self) -> None:
        self.runs: dict[str, dict[str, Any]] = {
            ACCEPTED_RUN: {
                "run_id": ACCEPTED_RUN,
                "status": "accepted",
                "accepted_by": "manager@firm",
                "accepted_at": "2026-10-31T12:30:00+05:30",
                "agent": "subsequent-receipts",
            },
            PROPOSED_RUN: {
                "run_id": PROPOSED_RUN,
                "status": "proposed",
                "accepted_by": None,
                "accepted_at": None,
            },
            REFUSED_RUN: {
                "run_id": REFUSED_RUN,
                "status": "refused",
                "accepted_by": None,
                "accepted_at": None,
                "decision_note": "duplicate of an earlier run",
            },
        }
        self.calls: list[Call] = []
        self.fail_with: int | None = None
        self.require_token = False
        self.non_json = False
        self.time_out = False
        self.transport = httpx.MockTransport(self.handle)

    def client(self, credential: str | None = None) -> WorkMindClient:
        return WorkMindClient(BASE, httpx.Client(transport=self.transport), credential)

    def non_get_calls(self) -> list[Call]:
        return [c for c in self.calls if c.method != "GET"]

    def handle(self, request: httpx.Request) -> httpx.Response:
        url = urlparse(str(request.url))
        self.calls.append(Call(request.method, url.path, dict(request.headers)))
        if self.time_out:
            raise httpx.ReadTimeout("WorkMind did not answer", request=request)
        if self.require_token and request.headers.get("Authorization") != f"Bearer {TOKEN}":
            return httpx.Response(401, json={"detail": "No credential"})
        if self.fail_with is not None:
            return httpx.Response(
                self.fail_with, json={"detail": {"message": "WorkMind is restarting"}}
            )
        if self.non_json:
            return httpx.Response(
                200, content=b"<html>login</html>", headers={"content-type": "text/html"}
            )
        if request.method != "GET":
            return httpx.Response(405, json={"detail": "Method Not Allowed"})
        parts = [p for p in url.path.split("/") if p]
        if len(parts) == 3 and parts[:2] == ["api", "runs"]:
            run_id = parts[2]
            record = self.runs.get(run_id)
            if record is None:
                # A fixture's run id with a per-test suffix is the same run (tests.helpers).
                known = next((k for k in self.runs if run_id.startswith(k)), None)
                record = {**self.runs[known], "run_id": run_id} if known else None
            if record is None:
                return httpx.Response(404, json={"detail": f"No run {run_id} exists"})
            return httpx.Response(200, json=record)
        return httpx.Response(404, json={"detail": "Not Found"})
