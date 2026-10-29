"""content_hash is deterministic and order-independent (spec 8.5: a hash can be recomputed)."""

from __future__ import annotations

import re

from hypothesis import given
from hypothesis import strategies as st

from oak_binder.hashing import canonical_json, content_hash, sha256_of_bytes

HEX64 = re.compile(r"^[0-9a-f]{64}$")

# sha256 of the two bytes "{}"
EMPTY_BODY_HASH = "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"
# sha256 of zero bytes
EMPTY_BYTES_HASH = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_known_vectors() -> None:
    assert content_hash({}) == EMPTY_BODY_HASH
    assert sha256_of_bytes(b"") == EMPTY_BYTES_HASH


def test_canonical_json_is_compact_sorted_and_keeps_unicode() -> None:
    assert canonical_json({"b": 1, "a": "₹ 1,00,000"}) == '{"a":"₹ 1,00,000","b":1}'


def test_key_order_does_not_change_the_hash() -> None:
    forward = {"title": "Cash", "conclusion": "Fairly stated", "sa_refs": ["SA 500"]}
    backward = {"sa_refs": ["SA 500"], "conclusion": "Fairly stated", "title": "Cash"}
    assert content_hash(forward) == content_hash(backward)


def test_different_content_gives_a_different_hash() -> None:
    assert content_hash({"conclusion": "Fairly stated"}) != content_hash(
        {"conclusion": "Fairly stated."}
    )


@given(st.dictionaries(st.text(), st.one_of(st.text(), st.integers(), st.none())))
def test_hash_is_64_hex_and_order_independent(body: dict[str, str | int | None]) -> None:
    digest = content_hash(body)
    assert HEX64.match(digest)
    reversed_body = dict(reversed(list(body.items())))
    assert content_hash(reversed_body) == digest
