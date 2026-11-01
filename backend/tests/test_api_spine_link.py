"""The binder's Spine link over the API (spec 3A; D29): set, change and clear while open,
verified against the Spine; frozen after assembly; an unlocked version is a named assembly
blocker, as is an unreachable Spine; the manifest records the link only when one exists;
the assembled event records the version's lock hash; reads are access-logged. Against
oak_binder_test with the Spine double."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.conftest import act_as, use_spine
from tests.fake_spine import (
    ENGAGEMENT_ID,
    LOCKED_HASH,
    LOCKED_VERSION_ID,
    OPEN_VERSION_ID,
    OTHER_ENGAGEMENT_ID,
    OTHER_VERSION_ID,
)
from tests.helpers import PARTNER, complete_binder, create_binder

pytestmark = pytest.mark.db


def patch(
    api: TestClient, binder_id: str, body: dict[str, Any], expected: int = 200
) -> dict[str, Any]:
    response = api.patch(f"/api/binders/{binder_id}", json=body)
    assert response.status_code == expected, f"{response.status_code} {response.text}"
    result: dict[str, Any] = response.json()
    return result


def link_of(api: TestClient, binder_id: str) -> dict[str, Any]:
    result: dict[str, Any] = api.get(f"/api/binders/{binder_id}/spine").json()
    return result


def blockers(api: TestClient, binder_id: str) -> dict[str, str]:
    status = api.get(f"/api/binders/{binder_id}/assembly").json()
    return {b["kind"]: b["detail"] for b in status["blockers"]}


def test_without_a_spine_the_binder_says_so_and_refuses_a_link(api: TestClient) -> None:
    binder = create_binder(api)
    link = link_of(api, binder["id"])
    assert link == {
        "configured": False,
        "engagement_id": None,
        "version_id": None,
        "reachable": False,
        "reason": None,
        "engagement": None,
        "version": None,
    }
    refused = patch(api, binder["id"], {"spine_engagement_id": str(ENGAGEMENT_ID)}, 409)
    assert "no Financial Spine is configured" in refused["detail"]
    assert api.get(f"/api/spine/engagements/{ENGAGEMENT_ID}/versions").status_code == 503


def test_link_engagement_then_version_verified_against_the_spine(api: TestClient) -> None:
    spine = use_spine(api)
    binder = create_binder(api)
    linked = patch(api, binder["id"], {"spine_engagement_id": str(ENGAGEMENT_ID)})
    assert (
        linked["spine_engagement_id"] == str(ENGAGEMENT_ID) and linked["spine_version_id"] is None
    )
    link = link_of(api, binder["id"])
    assert (
        link["configured"]
        and link["reachable"]
        and link["engagement"]["label"].startswith("FY 2025-26")
    )
    assert link["version"] is None

    # The version alone, now that the engagement is set.
    linked = patch(api, binder["id"], {"spine_version_id": str(OPEN_VERSION_ID)})
    assert linked["spine_version_id"] == str(OPEN_VERSION_ID)
    link = link_of(api, binder["id"])
    assert link["version"]["label"] == "Post-lock work" and link["version"]["is_locked"] is False

    # Refusals: unknown ids, a version of another engagement, a version without engagement.
    unknown = patch(
        api, binder["id"], {"spine_engagement_id": "99999999-9999-4999-8999-999999999999"}, 404
    )
    assert "No engagement" in unknown["detail"]
    wrong = patch(api, binder["id"], {"spine_version_id": str(OTHER_VERSION_ID)}, 422)
    assert (
        "belongs to engagement" in wrong["detail"] and str(OTHER_ENGAGEMENT_ID) in wrong["detail"]
    )
    assert patch(api, binder["id"], {"spine_version_id": "not-a-uuid"}, 422)
    # Nothing above changed the stored link.
    assert api.get(f"/api/binders/{binder['id']}").json()["spine_version_id"] == str(
        OPEN_VERSION_ID
    )

    # Clearing the engagement clears the version with it; the Spine was only ever read.
    cleared = patch(api, binder["id"], {"spine_engagement_id": None})
    assert cleared["spine_engagement_id"] is None and cleared["spine_version_id"] is None
    assert spine.non_get_calls() == []

    # The pass-through list for choosing a version.
    versions = api.get(f"/api/spine/engagements/{ENGAGEMENT_ID}/versions").json()
    assert [v["label"] for v in versions] == ["Post-lock work", "Final"]
    assert (
        api.get(f"/api/spine/engagements/{ENGAGEMENT_ID}").json()["label"].startswith("FY 2025-26")
    )


def test_an_unlocked_or_unreadable_version_blocks_assembly_by_name(api: TestClient) -> None:
    spine = use_spine(api)
    binder = complete_binder(api)
    patch(
        api,
        binder["id"],
        {"spine_engagement_id": str(ENGAGEMENT_ID), "spine_version_id": str(OPEN_VERSION_ID)},
    )
    found = blockers(api, binder["id"])
    assert "spine_version_unlocked" in found and "not locked" in found["spine_version_unlocked"]
    act_as(api, PARTNER)
    refused = api.post(f"/api/binders/{binder['id']}/assemble")
    assert refused.status_code == 409 and "spine_version_unlocked" in refused.json()["detail"]

    spine.fail_with = 503
    found = blockers(api, binder["id"])
    assert "spine_unreachable" in found
    assert link_of(api, binder["id"])["reachable"] is False
    spine.fail_with = None

    # Lock it in the Spine: the blocker goes, assembly records the version's lock hash.
    spine.lock(OPEN_VERSION_ID)
    assert "spine_version_unlocked" not in blockers(api, binder["id"])
    assembled = api.post(f"/api/binders/{binder['id']}/assemble")
    assert assembled.status_code == 200, assembled.text
    status = assembled.json()
    assert status["manifest"]["spine"] == {
        "engagement_id": str(ENGAGEMENT_ID),
        "version_id": str(OPEN_VERSION_ID),
    }
    event = status["events"][-1]
    assert event["kind"] == "assembled"
    assert event["details"]["spine_version"] == {
        "version_id": str(OPEN_VERSION_ID),
        "label": "Post-lock work",
        "hash": "e" * 64,
        "locked_at": "2026-10-30T18:00:00+05:30",
    }
    assert status["matches_recorded_manifest"] is True

    # Frozen after assembly: the link cannot change or be cleared.
    frozen = patch(api, binder["id"], {"spine_version_id": str(LOCKED_VERSION_ID)}, 409)
    assert "is assembled" in frozen["detail"]
    assert patch(api, binder["id"], {"spine_engagement_id": None}, 409)
    assert api.get(f"/api/binders/{binder['id']}").json()["spine_version_id"] == str(
        OPEN_VERSION_ID
    )
    # Reads of the link on an assembled file are in the access log.
    act_as(api, "quality.reviewer@firm")
    link_of(api, binder["id"])
    rows = api.get(f"/api/binders/{binder['id']}/assembly").json()["access"]
    assert [r["action"] for r in rows if r["user"] == "quality.reviewer@firm"] == [
        "spine link",
        "assembly status",
    ]


def test_a_linked_version_missing_from_the_spine_blocks_and_a_locked_one_passes(
    api: TestClient,
) -> None:
    spine = use_spine(api)
    binder = complete_binder(api)
    patch(
        api,
        binder["id"],
        {"spine_engagement_id": str(ENGAGEMENT_ID), "spine_version_id": str(LOCKED_VERSION_ID)},
    )
    assert blockers(api, binder["id"]) == {}
    del spine.versions[LOCKED_VERSION_ID]  # the Spine lost it (or the id was wrong all along)
    found = blockers(api, binder["id"])
    assert "spine_version_missing" in found and "No spine_version" in found["spine_version_missing"]


def test_a_binder_without_a_link_keeps_its_recorded_hash(api: TestClient) -> None:
    use_spine(api)
    binder = complete_binder(api)
    act_as(api, PARTNER)
    status = api.post(f"/api/binders/{binder['id']}/assemble").json()
    assert "spine" not in status["manifest"]
    assert "spine_version" not in status["events"][-1]["details"]
    assert status["matches_recorded_manifest"] is True
    assert LOCKED_HASH not in str(status["events"][-1]["details"])
