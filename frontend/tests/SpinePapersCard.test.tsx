import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import type { SpineAreaStatus, SpinePapersStatus } from "../src/api";
import { SpinePapersCard } from "../src/components/SpinePapersCard";
import { mockApi, SPINE_PAPERS_NONE } from "./mockApi";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function area(code: string, over: Partial<SpineAreaStatus> = {}): SpineAreaStatus {
  return {
    code,
    name: `Financial statement area ${code}`,
    mapped: false,
    listed_heads: [],
    paper_id: null,
    ref: `${code}-L`,
    state: "none",
    detail: null,
    recorded_version_id: null,
    recorded_version_label: null,
    ...over,
  };
}

const V = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";

const ready: SpinePapersStatus = {
  can_generate: true,
  reason: null,
  version_id: V,
  version_label: "Final",
  version_hash: "f".repeat(64),
  areas: [
    area("D", { mapped: true, listed_heads: ["BS.A.1"], paper_id: "p-d", state: "current" }),
    area("E", {
      mapped: true,
      listed_heads: ["BS.A.2"],
      paper_id: "p-e",
      state: "stale",
      detail: "built from Spine version 'Final' (aaaa); the binder is now linked to 'Post-lock work' (bbbb)",
      recorded_version_id: V,
      recorded_version_label: "Final",
    }),
    area("F", { mapped: true, listed_heads: ["PL.E.1"], paper_id: "p-f", state: "not_checked", detail: "freshness not checked: the Financial Spine could not answer" }),
    area("G", { mapped: true, listed_heads: ["BS.L.1"] }),
    ...[..."HIJKLMNOPQRST"].map((c) => area(c)),
  ],
  chain: {
    ref: "W-ADJ",
    section: "W",
    paper_id: null,
    state: "none",
    can_generate: true,
    reason: null,
    detail: null,
    recorded_version_id: null,
    recorded_version_label: null,
  },
  map_problems: [],
  unassigned_heads: ["PL.R.1"],
  map_source: "template",
  beyond_letters: [],
};

test("the card shows every mapped area with its state, links to the papers, and the chain", async () => {
  const onChanged = vi.fn(async () => undefined);
  mockApi({ "GET /api/binders/b1/spine-papers": ready });
  render(<SpinePapersCard binderId="b1" state="open" onChanged={onChanged} />);
  const card = await screen.findByTestId("spine-papers-card");
  expect(screen.getByTestId("spine-papers-version")).toHaveTextContent("Linked version Final");
  const rows = screen.getAllByTestId("spine-area");
  expect(rows.map((r) => r.textContent?.slice(0, 1))).toEqual(["D", "E", "F", "G"]);
  expect(within(rows[0]!).getByRole("link", { name: "D-L" })).toHaveAttribute("href", "#/papers/p-d");
  expect(within(rows[0]!).getByTestId("spine-paper-state")).toHaveTextContent("current");
  expect(within(rows[1]!).getByTestId("spine-paper-state")).toHaveTextContent("stale");
  expect(within(rows[1]!).getByTestId("spine-paper-detail")).toHaveTextContent("now linked to 'Post-lock work'");
  expect(within(rows[2]!).getByTestId("spine-paper-state")).toHaveTextContent("not checked");
  expect(within(rows[2]!).getByTestId("spine-paper-detail")).toHaveTextContent("could not answer");
  expect(within(rows[3]!).getByTestId("spine-paper-state")).toHaveTextContent("not generated");
  expect(within(rows[3]!).getByRole("button", { name: "Generate G-L" })).toBeEnabled();
  expect(screen.getByTestId("spine-papers-unmapped")).toHaveTextContent("13 area(s) have no heads in the area map: H, I, J");
  expect(screen.getByTestId("spine-papers-unassigned")).toHaveTextContent("PL.R.1");
  expect(screen.getByRole("button", { name: "Generate lead schedules (1)" })).toBeEnabled();
  const chain = screen.getByTestId("spine-chain");
  expect(chain).toHaveTextContent("W-ADJ");
  expect(within(chain).getByTestId("spine-paper-state")).toHaveTextContent("not generated");
  expect(within(chain).getByRole("button", { name: "Generate adjustment chain" })).toBeEnabled();
  expect(card).not.toHaveTextContent("cannot be generated");
  expect(onChanged).not.toHaveBeenCalled();
});

test("generating posts once per click and reloads the binder", async () => {
  const onChanged = vi.fn(async () => undefined);
  const calls = mockApi({
    "GET /api/binders/b1/spine-papers": ready,
    "POST /api/binders/b1/spine-papers/lead-schedules": [],
    "POST /api/binders/b1/spine-papers/adjustment-chain": {},
  });
  render(<SpinePapersCard binderId="b1" state="open" onChanged={onChanged} />);
  await screen.findByTestId("spine-papers-card");
  fireEvent.click(screen.getByRole("button", { name: "Generate G-L" }));
  await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
  fireEvent.click(screen.getByRole("button", { name: "Generate lead schedules (1)" }));
  await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(2));
  fireEvent.click(screen.getByRole("button", { name: "Generate adjustment chain" }));
  await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(3));
  const posts = calls.filter((c) => c.method === "POST");
  expect(posts.map((c) => [c.path, c.body])).toEqual([
    ["/api/binders/b1/spine-papers/lead-schedules", { areas: ["G"] }],
    ["/api/binders/b1/spine-papers/lead-schedules", { areas: null }],
    ["/api/binders/b1/spine-papers/adjustment-chain", undefined],
  ]);
});

test("a backend refusal is shown as said and the card recovers", async () => {
  mockApi({
    "GET /api/binders/b1/spine-papers": ready,
    "POST /api/binders/b1/spine-papers/lead-schedules": {
      httpStatus: 409,
      body: { detail: "run 'x' of spine was already received as paper G-L: one paper per run (spec 3C)" },
    },
  });
  render(<SpinePapersCard binderId="b1" state="open" onChanged={async () => undefined} />);
  await screen.findByTestId("spine-papers-card");
  fireEvent.click(screen.getByRole("button", { name: "Generate G-L" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("one paper per run");
  expect(screen.getByRole("button", { name: "Generate G-L" })).toBeEnabled();
});

test("when lead schedules cannot be generated the reason is shown and nothing is offered", async () => {
  mockApi({
    "GET /api/binders/b1/spine-papers": {
      ...ready,
      can_generate: false,
      reason: "no area map for template statutory: no Schedule III head is assigned to any area D-T, so no lead schedule can be generated (TEMPLATE_AUTHORING item 1)",
      areas: ready.areas.map((a) => area(a.code)),
      unassigned_heads: [],
      map_source: "none",
      beyond_letters: [],
    },
  });
  render(<SpinePapersCard binderId="b1" state="open" onChanged={async () => undefined} />);
  await screen.findByTestId("spine-papers-card");
  expect(screen.getByTestId("spine-papers-reason")).toHaveTextContent("no area map for template statutory");
  expect(screen.getByTestId("spine-papers-no-areas")).toHaveTextContent("TEMPLATE_AUTHORING item 1");
  expect(screen.queryByRole("button", { name: /Generate lead schedules/ })).not.toBeInTheDocument();
  // The chain needs no map: it is still offered.
  expect(screen.getByRole("button", { name: "Generate adjustment chain" })).toBeEnabled();
});

test("map problems and an unlocked version disable generation with the reasons shown", async () => {
  mockApi({
    "GET /api/binders/b1/spine-papers": {
      ...ready,
      can_generate: false,
      reason: "Spine version 'Post-lock work' is not locked: Spine papers are generated from a locked version only",
      map_problems: ["areas D and E both cover heads ['BS.A.2'] after expansion; a head belongs to one area"],
      chain: { ...ready.chain, can_generate: false, reason: "Spine version 'Post-lock work' is not locked" },
    },
  });
  render(<SpinePapersCard binderId="b1" state="open" onChanged={async () => undefined} />);
  await screen.findByTestId("spine-papers-card");
  expect(screen.getByTestId("spine-papers-reason")).toHaveTextContent("is not locked");
  expect(screen.getByTestId("spine-papers-problems")).toHaveTextContent("both cover heads");
  expect(screen.getByRole("button", { name: "Generate G-L" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Generate lead schedules (1)" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Generate adjustment chain" })).toBeDisabled();
  expect(screen.getByTestId("spine-chain-reason")).toHaveTextContent("is not locked");
});

test("an assembled binder shows the states read-only and says why nothing is offered", async () => {
  mockApi({ "GET /api/binders/b1/spine-papers": { ...ready, can_generate: false, reason: "the binder is assembled: Spine papers are generated while it is open" } });
  render(<SpinePapersCard binderId="b1" state="assembled" onChanged={async () => undefined} />);
  await screen.findByTestId("spine-papers-card");
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
  expect(screen.getByText(/A stale paper is information in the assembly status, never a blocker/)).toBeInTheDocument();
  expect(screen.getAllByTestId("spine-paper-state").map((b) => b.textContent)).toEqual(["current", "stale", "not checked", "not generated", "not generated"]);
});

test("an unlinked binder says so plainly", async () => {
  mockApi({ "GET /api/binders/b1/spine-papers": SPINE_PAPERS_NONE });
  render(<SpinePapersCard binderId="b1" state="open" onChanged={async () => undefined} />);
  await screen.findByTestId("spine-papers-card");
  expect(screen.getByTestId("spine-papers-reason")).toHaveTextContent("not linked to a Financial Spine version");
  expect(screen.getByTestId("spine-chain-reason")).toHaveTextContent("not linked");
  expect(screen.getByRole("button", { name: "Generate adjustment chain" })).toBeDisabled();
  expect(screen.queryByRole("button", { name: /lead schedules/ })).not.toBeInTheDocument();
});

test("a map derived from the Spine's tree is said so, with the groups beyond the letters", async () => {
  mockApi({
    "GET /api/binders/b1/spine-papers": {
      ...ready,
      map_source: "derived",
      beyond_letters: ["R.17", "R.18"],
      areas: ready.areas.map((a) => (a.code === "D" ? { ...a, name: "Assets", listed_heads: ["BS.A"] } : a)),
    },
  });
  render(<SpinePapersCard binderId="b1" state="open" onChanged={async () => undefined} />);
  await screen.findByTestId("spine-papers-card");
  expect(screen.getByTestId("spine-papers-derived")).toHaveTextContent("derived from the Spine's Schedule III tree (D38)");
  expect(screen.getByTestId("spine-papers-derived")).toHaveTextContent("2 head group(s) had no letter D–T left: R.17, R.18");
  expect(screen.getAllByTestId("spine-area")[0]).toHaveTextContent("D Assets");
});

test("the card refetches its status when the binder's Spine link changes", async () => {
  const calls = mockApi({ "GET /api/binders/b1/spine-papers": SPINE_PAPERS_NONE });
  const { rerender } = render(
    <SpinePapersCard binderId="b1" state="open" onChanged={async () => undefined} refreshKey="//open" />,
  );
  await screen.findByTestId("spine-papers-card");
  expect(calls.filter((c) => c.path === "/api/binders/b1/spine-papers")).toHaveLength(1);
  rerender(
    <SpinePapersCard binderId="b1" state="open" onChanged={async () => undefined} refreshKey="eng/ver/open" />,
  );
  await waitFor(() => expect(calls.filter((c) => c.path === "/api/binders/b1/spine-papers")).toHaveLength(2));
});
