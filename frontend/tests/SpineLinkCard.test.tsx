import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import type { SpineLink, SpineVersion } from "../src/api";
import { BinderPage } from "../src/pages/BinderPage";
import { SPINE_PAPERS_NONE, SPINE_UNCONFIGURED, binderFixture, mockApi } from "./mockApi";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const E = "11111111-1111-4111-8111-111111111111";
const V_LOCKED = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const V_OPEN = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";

const versions: SpineVersion[] = [
  {
    version_id: V_OPEN,
    engagement_id: E,
    version_no: 2,
    label: "Post-lock work",
    is_locked: false,
    locked_by: null,
    locked_at: null,
    hash: null,
    performance_materiality: null,
    pm_source: null,
    adjustments: null,
  },
  {
    version_id: V_LOCKED,
    engagement_id: E,
    version_no: 1,
    label: "Final",
    is_locked: true,
    locked_by: "partner@firm",
    locked_at: "2026-10-20T10:00:00+05:30",
    hash: "f".repeat(64),
    performance_materiality: "250000.00",
    pm_source: "C-1",
    adjustments: { proposed: 0, accepted: 2, refused: 1 },
  },
];

const linked: SpineLink = {
  configured: true,
  engagement_id: E,
  version_id: V_OPEN,
  reachable: true,
  reason: null,
  engagement: { id: E, entity_id: null, financial_year_end: "2026-03-31", label: "FY 2025-26 statutory audit" },
  version: versions[0]!,
};

const logs = { "GET /api/binders/b1/discussions": [], "GET /api/binders/b1/departures": [] };

test("an unconfigured Spine is said plainly and offers no form", async () => {
  mockApi({ "GET /api/binders/b1": binderFixture(), ...logs, "GET /api/binders/b1/spine-papers": SPINE_PAPERS_NONE, "GET /api/binders/b1/spine": SPINE_UNCONFIGURED });
  render(<BinderPage id="b1" />);
  await screen.findByTestId("spine-unconfigured");
  expect(screen.queryByRole("button", { name: "Save link" })).not.toBeInTheDocument();
});

test("a linked binder shows the engagement, the version and its lock state", async () => {
  mockApi({ "GET /api/binders/b1": binderFixture({ spine_engagement_id: E, spine_version_id: V_OPEN }), ...logs, "GET /api/binders/b1/spine-papers": SPINE_PAPERS_NONE, "GET /api/binders/b1/spine": linked });
  render(<BinderPage id="b1" />);
  const card = await screen.findByTestId("spine-link");
  expect(card).toHaveTextContent("FY 2025-26 statutory audit · year end 2026-03-31");
  expect(card).toHaveTextContent("Post-lock work");
  expect(card).toHaveTextContent("not locked — blocks assembly");
  expect(screen.getByRole("button", { name: "Clear link" })).toBeEnabled();
});

test("choosing a version loads the engagement's versions and saves the link", async () => {
  const calls = mockApi({
    "GET /api/binders/b1": binderFixture(),
    ...logs,
    "GET /api/binders/b1/spine-papers": SPINE_PAPERS_NONE, "GET /api/binders/b1/spine": () => (calls.some((c) => c.method === "PATCH") ? { ...linked, version_id: V_LOCKED, version: versions[1]! } : { ...SPINE_UNCONFIGURED, configured: true }),
    [`GET /api/spine/engagements/${E}/versions`]: versions,
    "PATCH /api/binders/b1": binderFixture({ spine_engagement_id: E, spine_version_id: V_LOCKED }),
  });
  render(<BinderPage id="b1" />);
  await screen.findByText("Not linked to a Spine engagement.");
  fireEvent.change(screen.getByLabelText("Spine engagement id"), { target: { value: E } });
  fireEvent.click(screen.getByRole("button", { name: "Load versions" }));
  const picker = await screen.findByTestId("spine-version");
  expect(picker.querySelectorAll("option")).toHaveLength(3);
  expect(picker).toHaveTextContent("1 · Final · locked");
  fireEvent.change(picker, { target: { value: V_LOCKED } });
  fireEvent.click(screen.getByRole("button", { name: "Save link" }));
  await waitFor(() => expect(screen.getByTestId("spine-link")).toHaveTextContent("locked 2026-10-20"));
  const patch = calls.find((c) => c.method === "PATCH");
  expect(patch?.body).toEqual({ spine_engagement_id: E, spine_version_id: V_LOCKED });
});

test("an unreachable Spine is reported and an assembled binder shows the link frozen", async () => {
  mockApi({
    "GET /api/binders/b1": binderFixture({ state: "assembled", spine_engagement_id: E, spine_version_id: V_LOCKED }),
    ...logs,
    "GET /api/binders/b1/spine-papers": SPINE_PAPERS_NONE, "GET /api/binders/b1/spine": { ...linked, reachable: false, reason: "the Financial Spine is unreachable", engagement: null, version: null },
  });
  render(<BinderPage id="b1" />);
  await screen.findByRole("status");
  expect(screen.getByRole("status")).toHaveTextContent("The Spine could not be read: the Financial Spine is unreachable");
  expect(screen.getByText(/frozen with the assembled file/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Save link" })).not.toBeInTheDocument();
});
