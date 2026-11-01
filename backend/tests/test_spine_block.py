"""The Spine provenance block (Stage E step E1, D32): what a Spine-produced paper's
``generated.spine`` carries, validated strictly; every figure a string the Spine served."""

from __future__ import annotations

import copy
from typing import Any

import pytest
from pydantic import ValidationError

from oak_binder.schemas.generated import Generated, SpineBlock
from tests.fake_spine import LOCKED_HASH, LOCKED_VERSION_ID

LEAD_SCHEDULE: dict[str, Any] = {
    "kind": "lead_schedule",
    "version_id": str(LOCKED_VERSION_ID),
    "version_label": "Final",
    "version_hash": LOCKED_HASH,
    "locked_at": "2026-10-20T10:00:00+05:30",
    "balances_hash": LOCKED_HASH,
    "tree_version": 3,
    "area": "D",
    "lines": [
        {
            "head_id": "BS.A.1",
            "label": "Cash and cash equivalents",
            "current": "1250000.00",
            "prior": None,
        }
    ],
    "ledgers": [
        {
            "head_id": "BS.A.1",
            "ledger_key": "hdfc-current",
            "ledger_name": "HDFC Bank current account",
            "parent_chain": ["Bank Accounts"],
            "unadjusted": "1200000.00",
            "reclass": "0.00",
            "corrections": "50000.00",
            "adjusted": "1250000.00",
            "prior_closing": "900000.00",
        }
    ],
    "head_totals": [
        {
            "head_id": "BS.A.1",
            "ledgers": 2,
            "unadjusted": "1200000.00",
            "adjusted": "1250000.00",
            "prior_closing": "912000.00",
        }
    ],
    "heads_without_ledgers": ["PL.E.1"],
    "adjustments": [
        {
            "adjustment_id": "adj-0001",
            "kind": "correction",
            "status": "accepted",
            "narration": "Unrecorded bank interest",
            "working_paper_ref": "D-1",
            "proposed_by": "senior@firm",
            "lines": [
                {
                    "line_no": 1,
                    "ledger_key": "hdfc-current",
                    "head_id": "BS.A.1",
                    "dr": "50000.00",
                    "cr": "0.00",
                }
            ],
        }
    ],
}

ADJUSTMENT_CHAIN: dict[str, Any] = {
    "kind": "adjustment_chain",
    "version_id": str(LOCKED_VERSION_ID),
    "version_label": "Final",
    "version_hash": LOCKED_HASH,
    "adjustments": LEAD_SCHEDULE["adjustments"],
    "uncorrected": {
        "aggregate": "15000.00",
        "performance_materiality": "250000.00",
        "gate": "open",
    },
}


def block(base: dict[str, Any], **changes: Any) -> dict[str, Any]:
    out = copy.deepcopy(base)
    out.update(changes)
    return out


def test_a_lead_schedule_block_is_accepted_with_its_figures_as_strings() -> None:
    parsed = SpineBlock.model_validate(LEAD_SCHEDULE)
    assert parsed.area == "D" and parsed.ledgers[0].adjusted == "1250000.00"
    assert parsed.lines[0].prior is None and parsed.heads_without_ledgers == ["PL.E.1"]
    assert parsed.adjustments[0].status == "accepted"


def test_an_adjustment_chain_block_is_accepted_with_the_uncorrected_schedule_as_served() -> None:
    parsed = SpineBlock.model_validate(ADJUSTMENT_CHAIN)
    assert parsed.area is None and parsed.uncorrected == ADJUSTMENT_CHAIN["uncorrected"]


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"area": None}, "names its area"),
        ({"area": "  "}, "names its area"),
        ({"uncorrected": {"gate": "open"}}, "carries no uncorrected schedule"),
        ({"version_hash": ""}, "version_hash must not be blank"),
        (
            {
                "ledgers": [
                    {
                        "head_id": "BS.A.1",
                        "ledger_key": "k",
                        "ledger_name": "n",
                        "adjusted": 1250000,
                    }
                ]
            },
            "adjusted",
        ),
        ({"lines": [{"head_id": "BS.A.1", "label": "x", "current": 12.5}]}, "current"),
        ({"confidence": 0.95}, "confidence"),
    ],
)
def test_a_lead_schedule_block_is_refused_when_malformed(
    changes: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        SpineBlock.model_validate(block(LEAD_SCHEDULE, **changes))


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"uncorrected": None}, "carries the uncorrected schedule"),
        ({"area": "W"}, "belongs to no single area"),
        ({"lines": LEAD_SCHEDULE["lines"]}, "carries no area lines"),
    ],
)
def test_an_adjustment_chain_block_is_refused_when_malformed(
    changes: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        SpineBlock.model_validate(block(ADJUSTMENT_CHAIN, **changes))


def test_the_generated_block_takes_a_spine_block_for_source_spine_and_only_then() -> None:
    generated: dict[str, Any] = {
        "source": "spine",
        "module": "oak_spine",
        "generated_at": "2026-10-31T10:00:00+05:30",
        "inputs": {"version_id": str(LOCKED_VERSION_ID), "area": "D"},
        "citations": [{"source": "Financial Spine", "head_id": "BS.A.1"}],
        "spine": LEAD_SCHEDULE,
    }
    assert Generated.model_validate(generated).spine is not None
    with pytest.raises(ValidationError, match="needs its spine block"):
        Generated.model_validate({k: v for k, v in generated.items() if k != "spine"})
    with pytest.raises(ValidationError, match="a sampling paper carries no spine block"):
        Generated.model_validate(
            {**generated, "source": "sampling", "sampling": {"formula": "f", "seed": 1}}
        )
