"""Content hashing for working paper versions (spec 4: content_hash; spec 8.5).

The hash covers a canonical JSON rendering of the version body: keys sorted, no insignificant
whitespace, non-ASCII kept as-is. Two bodies with the same content always hash the same,
whatever order their keys were written in, so a hash can be recomputed years later and
compared.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any


def canonical_json(body: Mapping[str, Any]) -> str:
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_hash(body: Mapping[str, Any]) -> str:
    """SHA-256 of the canonical JSON body, as 64 lowercase hex characters."""
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def sha256_of_bytes(data: bytes) -> str:
    """SHA-256 of raw file bytes, for attachments and the assembly manifest."""
    return hashlib.sha256(data).hexdigest()
