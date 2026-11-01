"""The Spine's Schedule III tree and the richer Spine double (Stage E step E1, D32): the
client reads ``GET /api/tree`` with every head's explicit parent; balances, adjustments and
the uncorrected schedule are served as ``oak_spine`` shapes them. No database, no network."""

from __future__ import annotations

import pytest

from oak_binder.errors import SpineUnavailable
from oak_binder.services.spine_client import parse_tree
from tests.fake_spine import LOCKED_HASH, LOCKED_VERSION_ID, OPEN_VERSION_ID, FakeSpine


def test_the_client_reads_the_tree_with_explicit_parents() -> None:
    spine = FakeSpine()
    tree = spine.client().tree()
    assert tree.division == "I" and tree.version == 3
    by_id = tree.by_id()
    assert by_id["BS"].parent is None and by_id["BS.A"].parent == "BS"
    assert by_id["X.ODD"].parent == "BS.A.2"  # the parent field, not the id, says where it sits
    assert by_id["BS.A.1"].mappable is True and by_id["BS.A"].mappable is False
    assert by_id["PL.R.1"].label == "Revenue from operations"
    assert [c.path for c in spine.calls] == ["/api/tree"]
    assert spine.non_get_calls() == []


def test_parse_tree_keeps_parents_as_served_and_refuses_an_unexpected_answer() -> None:
    tree = parse_tree({"heads": [{"id": "A", "parent": None}, {"id": "B", "parent": "A"}]})
    assert [(h.id, h.parent, h.label, h.mappable) for h in tree.heads] == [
        ("A", None, "A", False),
        ("B", "A", "B", False),
    ]
    assert tree.division is None and tree.version is None
    bad: object
    for bad in ({}, {"heads": "x"}, {"heads": [{"parent": "A"}]}, {"heads": [{"id": ""}]}, []):
        with pytest.raises(SpineUnavailable, match="Schedule III tree"):
            parse_tree(bad)


def test_the_double_serves_balances_adjustments_and_uncorrected_as_the_spine_shapes_them() -> None:
    client = FakeSpine().client()
    balances = client.balances(LOCKED_VERSION_ID)
    assert balances["source"] == "stored" and balances["hash"] == LOCKED_HASH
    heads = [ledger["head_id"] for ledger in balances["ledgers"]]
    assert heads == ["BS.A.1", "BS.A.1", "BS.A.2.1", "BS.L.1", "PL.R.1", None]
    # Every figure is a string the Spine produced; a zero is "0.00", an absent prior is None.
    for ledger in balances["ledgers"]:
        for key in ("unadjusted", "reclass", "corrections", "adjusted"):
            assert isinstance(ledger[key], str)
    assert balances["ledgers"][2]["adjusted"] == "0.00"
    assert balances["ledgers"][5]["prior_closing"] is None
    assert [g["head_id"] for g in balances["groups"]] == [
        "BS.A.1",
        "BS.A.2.1",
        "BS.L.1",
        "PL.R.1",
        None,
    ]
    assert "PL.E.1" not in heads  # a head of the tree with no ledger entry at all

    open_balances = client.balances(OPEN_VERSION_ID)
    assert open_balances["source"] == "computed" and open_balances["hash"] is None

    adjustments = client.adjustments(LOCKED_VERSION_ID)
    assert [a["status"] for a in adjustments] == ["accepted", "proposed", "refused"]
    assert [a["working_paper_ref"] for a in adjustments] == ["D-1", "D-9", "D-1"]
    assert all(isinstance(line["dr"], str) for a in adjustments for line in a["lines"])
    assert [a["status"] for a in client.adjustments(LOCKED_VERSION_ID, status="refused")] == [
        "refused"
    ]

    uncorrected = client.uncorrected(LOCKED_VERSION_ID)
    assert uncorrected["performance_materiality"] == "250000.00"
    assert uncorrected["aggregate"] == "15000.00" and uncorrected["gate"] == "open"
    assert uncorrected["uncorrected"][0]["adjustment_id"] == "adj-0003"
