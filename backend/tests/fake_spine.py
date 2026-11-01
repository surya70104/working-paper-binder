"""A Financial Spine double for the Stage B client (D29): the read endpoints the Binder uses,
behind ``httpx.MockTransport``, serving records shaped exactly like ``oak_spine``'s own
``version_json``, engagement and presentation output. Records every call so tests can assert
the client never sends anything but GET, and can misbehave on request: a status of choice,
a required bearer token, a timeout, a non-JSON body."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx

from oak_binder.services.spine_client import SpineClient

BASE = "http://127.0.0.1:8000"
TOKEN = "fake-spine-token"  # noqa: S105

ENGAGEMENT_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
OTHER_ENGAGEMENT_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
LOCKED_VERSION_ID = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
OPEN_VERSION_ID = uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
OTHER_VERSION_ID = uuid.UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
LOCKED_HASH = "f" * 64


@dataclass
class Call:
    method: str
    path: str
    headers: dict[str, str] = field(default_factory=dict)


def version_record(
    version_id: uuid.UUID,
    engagement_id: uuid.UUID,
    *,
    version_no: int,
    label: str,
    locked: bool,
) -> dict[str, Any]:
    return {
        "version_id": str(version_id),
        "engagement_id": str(engagement_id),
        "entity_id": "33333333-3333-4333-8333-333333333333",
        "base_import_id": "44444444-4444-4444-8444-444444444444",
        "version_no": version_no,
        "label": label,
        "supersedes_id": None,
        "supersede_reason": None,
        "prior_version_id": None,
        "performance_materiality": "250000.00" if locked else None,
        "pm_source": "C-1 Materiality memo" if locked else None,
        "is_locked": locked,
        "locked_by": "partner@firm" if locked else None,
        "locked_at": "2026-10-20T10:00:00+05:30" if locked else None,
        "hash": LOCKED_HASH if locked else None,
        "tree_version": 3,
        "snapshot_sha256": LOCKED_HASH if locked else None,
        "created_by": "manager@firm",
        "created_at": "2026-10-19T09:00:00+05:30",
        "adjustments": {"proposed": 0, "accepted": 2, "refused": 1},
    }


def presentation_record(version_id: uuid.UUID, locked: bool) -> dict[str, Any]:
    def line(head_id: str, label: str, side: str, depth: int, current: str) -> dict[str, Any]:
        return {
            "head_id": head_id,
            "parent": None,
            "depth": depth,
            "label": label,
            "item": None,
            "note": None,
            "side": side,
            "basis": "closing",
            "mappable": True,
            "current": current,
            "prior": None,
            "signed_current": current,
            "signed_prior": None,
            "rounded_current": current,
            "rounded_prior": None,
            "has_figures": True,
        }

    return {
        "version_id": str(version_id),
        "base_import_id": "44444444-4444-4444-8444-444444444444",
        "division": "I",
        "is_locked": locked,
        "provisional": not locked,
        "basis": "stored" if locked else "computed",
        "tree_version": 3,
        "tree_version_current": 3,
        "tree_matches": True,
        "hash": LOCKED_HASH if locked else None,
        "integrity": None,
        "prior": None,
        "status": "ready",
        "blocks": [],
        "rounding": {"unit": "1"},
        "balance_sheet": {
            "lines": [
                line("BS.A.1", "Cash and cash equivalents", "assets", 2, "1250000.00"),
                line("BS.L.1", "Trade payables", "liabilities", 2, "480000.00"),
                {"id": "BS.TOTAL", "label": "Total", "current": "1730000.00"},  # computed
            ]
        },
        "profit_and_loss": {
            "lines": [line("PL.R.1", "Revenue from operations", "income", 1, "9800000.00")]
        },
        "notes": None,
        "regrouping_note": None,
    }


def tree_record() -> dict[str, Any]:
    """``GET /api/tree`` as ``oak_spine.api.schedule3`` shapes it: every head with its explicit
    ``parent``, parents before children. One head, ``X.ODD``, sits under ``BS.A.2`` with an id
    that shares nothing with its parent's, so a test can prove descent is read from ``parent``
    and never from the id's shape (D32)."""

    def head(
        head_id: str, parent: str | None, label: str, side: str, depth: int, mappable: bool
    ) -> dict[str, Any]:
        return {
            "id": head_id,
            "parent": parent,
            "label": label,
            "statement": "balance_sheet" if head_id.startswith("BS") else "profit_and_loss",
            "nature": "debit" if side in ("assets", "expense") else "credit",
            "side": side,
            "item": None,
            "note": None,
            "mappable": mappable,
            "basis": "statute",
            "depth": depth,
        }

    return {
        "division": "I",
        "version": 3,
        "heads": [
            head("BS", None, "Balance sheet", "assets", 0, False),
            head("BS.A", "BS", "Assets", "assets", 1, False),
            head("BS.A.1", "BS.A", "Cash and cash equivalents", "assets", 2, True),
            head("BS.A.2", "BS.A", "Trade receivables", "assets", 2, False),
            head("X.ODD", "BS.A.2", "Receivables from related parties", "assets", 3, True),
            head("BS.A.2.1", "BS.A.2", "Other trade receivables", "assets", 3, True),
            head("BS.L", "BS", "Liabilities", "liabilities", 1, False),
            head("BS.L.1", "BS.L", "Trade payables", "liabilities", 2, True),
            head("PL", None, "Statement of profit and loss", "income", 0, False),
            head("PL.R", "PL", "Revenue", "income", 1, False),
            head("PL.R.1", "PL.R", "Revenue from operations", "income", 2, True),
            head("PL.E", "PL", "Expenses", "expense", 1, False),
            head("PL.E.1", "PL.E", "Cost of materials consumed", "expense", 2, True),
        ],
    }


def balances_record(version_id: uuid.UUID, locked: bool) -> dict[str, Any]:
    """``GET …/balances`` as ``oak_spine.spine.chain`` shapes it: every ledger's chain with its
    head, then the Spine's own per-head totals. Heads with figures of zero (``BS.A.2.1``), a
    head with no ledger at all (``PL.E.1``) and one unmapped ledger are deliberate."""

    def ledger(
        line_no: int, key: str, name: str, head_id: str | None, chain: list[str], **amounts: str
    ) -> dict[str, Any]:
        return {
            "line_no": line_no,
            "ledger_key": key,
            "ledger_name": name,
            "parent_chain": chain,
            "in_import": True,
            "absent": False,
            "head_id": head_id,
            "face_head": None,
            "sub_head": None,
            "nature": None,
            "side": None,
            "opening": None,
            "movement": None,
            "unadjusted": amounts.get("unadjusted", "0.00"),
            "reclass": amounts.get("reclass", "0.00"),
            "corrections": amounts.get("corrections", "0.00"),
            "adjusted": amounts.get("adjusted", "0.00"),
            "prior_closing": amounts.get("prior_closing"),
            "prior_regrouped": None,
            "regroup_reason": None,
        }

    def group(
        head_id: str | None, count: int, unadjusted: str, adjusted: str, prior: str | None
    ) -> dict[str, Any]:
        return {
            "head_id": head_id,
            "face_head": None,
            "sub_head": None,
            "nature": None,
            "ledgers": count,
            "unadjusted": unadjusted,
            "adjusted": adjusted,
            "prior_closing": prior,
        }

    return {
        "version_id": str(version_id),
        "base_import_id": "44444444-4444-4444-8444-444444444444",
        "is_locked": locked,
        "source": "stored" if locked else "computed",
        "tree_version": 3,
        "hash": LOCKED_HASH if locked else None,
        "ledgers": [
            ledger(
                1,
                "hdfc-current",
                "HDFC Bank current account",
                "BS.A.1",
                ["Bank Accounts"],
                unadjusted="1200000.00",
                adjusted="1250000.00",
                corrections="50000.00",
                prior_closing="900000.00",
            ),
            ledger(
                2,
                "cash-in-hand",
                "Cash in hand",
                "BS.A.1",
                ["Cash-in-Hand"],
                unadjusted="0.00",
                adjusted="0.00",
                prior_closing="12000.00",
            ),
            ledger(
                3,
                "customer-a",
                "Customer A",
                "BS.A.2.1",
                ["Sundry Debtors"],
                unadjusted="0.00",
                adjusted="0.00",
                prior_closing="0.00",
            ),
            ledger(
                4,
                "supplier-z",
                "Supplier Z",
                "BS.L.1",
                ["Sundry Creditors"],
                unadjusted="480000.00",
                adjusted="480000.00",
                prior_closing="410000.00",
            ),
            ledger(
                5,
                "sales-domestic",
                "Sales - domestic",
                "PL.R.1",
                ["Sales Accounts"],
                unadjusted="9850000.00",
                reclass="0.00",
                corrections="-50000.00",
                adjusted="9800000.00",
                prior_closing="9100000.00",
            ),
            ledger(
                6,
                "suspense",
                "Suspense",
                None,
                ["Suspense A/c"],
                unadjusted="1500.00",
                adjusted="1500.00",
            ),
        ],
        "groups": [
            group("BS.A.1", 2, "1200000.00", "1250000.00", "912000.00"),
            group("BS.A.2.1", 1, "0.00", "0.00", "0.00"),
            group("BS.L.1", 1, "480000.00", "480000.00", "410000.00"),
            group("PL.R.1", 1, "9850000.00", "9800000.00", "9100000.00"),
            group(None, 1, "1500.00", "1500.00", None),
        ],
        "unmapped": {"count": 1, "value": "1500.00"},
        "totals": {"unadjusted": "11531500.00", "adjusted": "11531500.00"},
        "count": 6,
    }


def adjustments_record(version_id: uuid.UUID) -> list[dict[str, Any]]:
    """``GET …/adjustments`` as ``oak_spine.spine.adjustments.adjustment_json`` shapes it: all
    three statuses, each naming a working paper (one that a test binder will have, one that
    none will)."""

    def line(line_no: int, key: str, name: str, head_id: str, dr: str, cr: str) -> dict[str, Any]:
        return {
            "line_no": line_no,
            "ledger_key": key,
            "ledger_name": name,
            "parent_chain": [],
            "head_id": head_id,
            "in_import": True,
            "dr": dr,
            "cr": cr,
        }

    def adjustment(
        adj_id: str,
        kind: str,
        status: str,
        narration: str,
        wp_ref: str,
        lines: list[dict[str, Any]],
        decided: bool,
    ) -> dict[str, Any]:
        return {
            "adjustment_id": adj_id,
            "version_id": str(version_id),
            "kind": kind,
            "status": status,
            "narration": narration,
            "working_paper_ref": wp_ref,
            "finding_ref": None,
            "proposed_by": "senior@firm",
            "proposed_at": "2026-10-18T11:00:00+05:30",
            "decided_by": "partner@firm" if decided else None,
            "decided_at": "2026-10-19T09:30:00+05:30" if decided else None,
            "decision_note": "Agreed" if decided else None,
            "copied_from_id": None,
            "lines": lines,
        }

    return [
        adjustment(
            "adj-0001",
            "correction",
            "accepted",
            "Unrecorded bank interest",
            "D-1",
            [
                line(1, "hdfc-current", "HDFC Bank current account", "BS.A.1", "50000.00", "0.00"),
                line(2, "sales-domestic", "Sales - domestic", "PL.R.1", "0.00", "50000.00"),
            ],
            True,
        ),
        adjustment(
            "adj-0002",
            "reclass",
            "proposed",
            "Regroup related-party receivable",
            "D-9",
            [
                line(1, "customer-a", "Customer A", "BS.A.2.1", "0.00", "25000.00"),
                line(2, "related-party", "Related party receivable", "X.ODD", "25000.00", "0.00"),
            ],
            False,
        ),
        adjustment(
            "adj-0003",
            "correction",
            "refused",
            "Cut-off: March invoice",
            "D-1",
            [
                line(1, "sales-domestic", "Sales - domestic", "PL.R.1", "15000.00", "0.00"),
                line(2, "customer-a", "Customer A", "BS.A.2.1", "0.00", "15000.00"),
            ],
            True,
        ),
    ]


def uncorrected_record(version_id: uuid.UUID, locked: bool) -> dict[str, Any]:
    """``GET …/uncorrected`` as ``oak_spine.spine.uncorrected.schedule_json`` keys it (D22):
    the misstatements not accepted, gross aggregate, performance materiality, headroom, gate."""
    return {
        "version_id": str(version_id),
        "is_locked": locked,
        "basis": "gross",
        "performance_materiality": "250000.00",
        "uncorrected": [
            {
                "adjustment_id": "adj-0003",
                "kind": "correction",
                "status": "refused",
                "narration": "Cut-off: March invoice",
                "working_paper_ref": "D-1",
                "measure": "15000.00",
                "profit_effect": "-15000.00",
                "profit_effect_partial": False,
            }
        ],
        "unposted_reclassifications": [
            {
                "adjustment_id": "adj-0002",
                "status": "proposed",
                "narration": "Regroup related-party receivable",
                "working_paper_ref": "D-9",
                "measure": "25000.00",
            }
        ],
        "aggregate": "15000.00",
        "headroom": "235000.00",
        "gate": "open",
        "counts": {"proposed": 1, "accepted": 1, "refused": 1},
        "proposed": 1,
        "refused": 1,
    }


class FakeSpine:
    def __init__(self) -> None:
        self.engagements: dict[uuid.UUID, dict[str, Any]] = {
            ENGAGEMENT_ID: {
                "id": str(ENGAGEMENT_ID),
                "entity_id": "33333333-3333-4333-8333-333333333333",
                "financial_year_end": "2026-03-31",
                "label": "FY 2025-26 statutory audit",
                "created_at": "2026-04-01T09:00:00+05:30",
            },
            OTHER_ENGAGEMENT_ID: {
                "id": str(OTHER_ENGAGEMENT_ID),
                "entity_id": "33333333-3333-4333-8333-333333333333",
                "financial_year_end": "2025-03-31",
                "label": "FY 2024-25 statutory audit",
                "created_at": "2025-04-01T09:00:00+05:30",
            },
        }
        self.versions: dict[uuid.UUID, dict[str, Any]] = {
            LOCKED_VERSION_ID: version_record(
                LOCKED_VERSION_ID, ENGAGEMENT_ID, version_no=1, label="Final", locked=True
            ),
            OPEN_VERSION_ID: version_record(
                OPEN_VERSION_ID, ENGAGEMENT_ID, version_no=2, label="Post-lock work", locked=False
            ),
            OTHER_VERSION_ID: version_record(
                OTHER_VERSION_ID, OTHER_ENGAGEMENT_ID, version_no=1, label="Prior", locked=True
            ),
        }
        self.calls: list[Call] = []
        self.fail_with: int | None = None
        self.require_token = False
        self.non_json = False
        self.time_out = False
        self.transport = httpx.MockTransport(self.handle)

    def client(self, credential: str | None = None) -> SpineClient:
        return SpineClient(BASE, httpx.Client(transport=self.transport), credential)

    def lock(self, version_id: uuid.UUID) -> None:
        record = self.versions[version_id]
        record.update(
            is_locked=True,
            locked_by="partner@firm",
            locked_at="2026-10-30T18:00:00+05:30",
            hash="e" * 64,
            snapshot_sha256="e" * 64,
        )

    def non_get_calls(self) -> list[Call]:
        return [c for c in self.calls if c.method != "GET"]

    def _json(self, status: int, payload: Any) -> httpx.Response:
        return httpx.Response(status, json=payload)

    def _not_found(self, kind: str, record_id: str) -> httpx.Response:
        return self._json(
            404,
            {"detail": {"code": f"{kind}.not_found", "message": f"No {kind} {record_id} exists"}},
        )

    def handle(self, request: httpx.Request) -> httpx.Response:
        url = urlparse(str(request.url))
        self.calls.append(Call(request.method, url.path, dict(request.headers)))
        if self.time_out:
            raise httpx.ReadTimeout("the Spine did not answer", request=request)
        if self.require_token and request.headers.get("Authorization") != f"Bearer {TOKEN}":
            return self._json(
                401, {"detail": {"code": "auth.required", "message": "No credential"}}
            )
        if self.fail_with is not None:
            return self._json(
                self.fail_with,
                {
                    "detail": {
                        "code": "database.unavailable",
                        "message": "The database could not be reached",
                    }
                },
            )
        if self.non_json:
            return httpx.Response(
                200, content=b"<html>login</html>", headers={"content-type": "text/html"}
            )
        if request.method != "GET":
            return self._json(405, {"detail": {"code": "method", "message": "Method Not Allowed"}})
        parts = [p for p in url.path.split("/") if p]
        if parts == ["api", "health"]:
            return self._json(200, {"status": "ok", "version": "0.9.0"})
        if parts == ["api", "tree"]:
            return self._json(200, tree_record())
        if len(parts) >= 3 and parts[:2] == ["api", "engagements"]:
            try:
                engagement_id = uuid.UUID(parts[2])
            except ValueError:
                return self._json(422, {"detail": "not a uuid"})
            record = self.engagements.get(engagement_id)
            if record is None:
                return self._not_found("engagement", parts[2])
            if len(parts) == 3:
                return self._json(200, record)
            if parts[3] == "spine-versions":
                listed = [
                    v for v in self.versions.values() if v["engagement_id"] == str(engagement_id)
                ]
                listed.sort(key=lambda v: -int(v["version_no"]))
                return self._json(200, listed)
        if len(parts) >= 3 and parts[:2] == ["api", "spine-versions"]:
            try:
                version_id = uuid.UUID(parts[2])
            except ValueError:
                return self._json(422, {"detail": "not a uuid"})
            record = self.versions.get(version_id)
            if record is None:
                return self._not_found("spine_version", parts[2])
            if len(parts) == 3:
                return self._json(200, record)
            tail = parts[3]
            if tail == "presentation":
                return self._json(200, presentation_record(version_id, bool(record["is_locked"])))
            if tail == "balances":
                return self._json(200, balances_record(version_id, bool(record["is_locked"])))
            if tail == "adjustments":
                wanted = dict(httpx.QueryParams(url.query)).get("status")
                listed = adjustments_record(version_id)
                if wanted:
                    listed = [a for a in listed if a["status"] == wanted]
                return self._json(200, listed)
            if tail == "uncorrected":
                return self._json(200, uncorrected_record(version_id, bool(record["is_locked"])))
        return self._json(404, {"detail": {"code": "route.not_found", "message": "No such route"}})
