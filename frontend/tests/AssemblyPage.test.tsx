import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { AssemblyPage } from "../src/pages/AssemblyPage";
import { assemblyFixture, mockApi } from "./mockApi";

afterEach(() => vi.unstubAllGlobals());

const HASH = "f".repeat(64);

const assembled = assemblyFixture({
  state: "assembled",
  assembled_at: "2026-11-01T10:00:00Z",
  assembly_hash: HASH,
  matches_recorded_manifest: true,
  blockers: [],
  manifest: {
    papers: [
      { ref: "A-1", title: "Acceptance", version: 3, content_hash: "a".repeat(64), attachments: [] },
      { ref: "C-1", title: "Materiality memo", version: 3, content_hash: "c".repeat(64), attachments: [{ filename: "benchmark.csv", sha256: "b".repeat(64) }] },
    ],
  },
  events: [{ id: "e1", kind: "assembled", actor: "partner@firm", at: "2026-11-01T10:00:00Z", reason: null, details: {} }],
});

test("blockers are named and Assemble is disabled while anything blocks", async () => {
  mockApi({ "GET /api/binders/b1/assembly": assemblyFixture() });
  render(<AssemblyPage id="b1" />);
  await screen.findByRole("heading", { name: /Assembly/ });
  const blockers = screen.getByTestId("blockers");
  expect(blockers).toHaveTextContent("Missing required paper A-1: Acceptance and continuance");
  expect(blockers).toHaveTextContent("Paper not signed off C-1: status is in_review");
  expect(screen.getByText(/cross-references to FS lines: the binder is not linked to a Financial Spine version/)).toBeInTheDocument();
  expect(screen.queryByText(/open review notes: review notes are Pass 2/)).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Assemble" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Purge content" })).toBeDisabled();
  expect(screen.getByText(/32 days left/)).toBeInTheDocument();
});

test("an assembled file shows its manifest, hash, verification and produce link", async () => {
  const calls = mockApi({
    "GET /api/binders/b1/assembly": assembled,
    "GET /api/binders/b1/verify": {
      ok: true,
      assembly_hash: HASH,
      recomputed_from_recorded_manifest: HASH,
      current_file_hash: HASH,
      current_matches_assembled: true,
      checks: [{ item: "assembly manifest", ok: true, detail: "reproduces" }],
    },
  });
  render(<AssemblyPage id="b1" />);
  await screen.findByRole("heading", { name: /Assembly/ });
  expect(screen.getByTestId("state")).toHaveTextContent("assembled");
  expect(screen.getByTestId("hash")).toHaveTextContent(HASH);
  expect(screen.getByText("Nothing blocks assembly.")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Produce file (zip)" })).toHaveAttribute(
    "href",
    "/api/binders/b1/produce",
  );
  expect(screen.getByText("benchmark.csv")).toBeInTheDocument();
  expect(screen.getAllByTestId("event")[0]).toHaveTextContent("assembled · partner@firm");

  fireEvent.click(screen.getByRole("button", { name: "Verify hashes" }));
  await waitFor(() => expect(screen.getByTestId("verification")).toHaveTextContent("Every recorded hash reproduces."));
  expect(calls.some((c) => c.path === "/api/binders/b1/verify")).toBe(true);
});

test("an open binder shows no access log; an assembled one lists who opened it", async () => {
  mockApi({ "GET /api/binders/b1/assembly": assemblyFixture() });
  const open = render(<AssemblyPage id="b1" />);
  await screen.findByRole("heading", { name: /Assembly/ });
  expect(screen.queryByRole("heading", { name: "Access log" })).not.toBeInTheDocument();
  open.unmount();

  mockApi({
    "GET /api/binders/b1/assembly": {
      ...assembled,
      access: [
        { user: "partner@firm", action: "binder", at: "2026-11-02T09:00:00Z" },
        { user: "nfra.inspector", action: "attachment benchmark.csv of C-1", at: "2026-11-03T11:30:00Z" },
      ],
    },
  });
  render(<AssemblyPage id="b1" />);
  await screen.findByRole("heading", { name: "Access log" });
  const rows = screen.getAllByTestId("access");
  expect(rows).toHaveLength(2);
  expect(rows[0]).toHaveTextContent("partner@firm · binder · 2026-11-02T09:00:00Z");
  expect(rows[1]).toHaveTextContent("nfra.inspector · attachment benchmark.csv of C-1");
});

test("purge needs retention to have expired and a confirmation", async () => {
  const calls = mockApi({
    "GET /api/binders/b1/assembly": { ...assembled, purge_allowed: true },
    "POST /api/binders/b1/purge": { ...assembled, state: "purged" },
  });
  render(<AssemblyPage id="b1" />);
  await screen.findByRole("heading", { name: /Assembly/ });
  const purge = screen.getByRole("button", { name: "Purge content" });
  expect(purge).toBeEnabled();
  fireEvent.click(purge);
  expect(calls.some((c) => c.method === "POST")).toBe(false); // nothing sent yet
  expect(screen.getByText(/destroys every attachment/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Confirm purge" }));
  await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "/api/binders/b1/purge")).toBe(true));
});

test("production is withheld while amendments are pending re-assembly", async () => {
  mockApi({
    "GET /api/binders/b1/assembly": {
      ...assembled,
      matches_recorded_manifest: false,
      blockers: [{ kind: "unsigned_paper", ref: "C-1", detail: "status is draft" }],
      events: [
        ...assembled.events,
        { id: "e2", kind: "amended", actor: "partner@firm", at: "2026-11-02T10:00:00Z", reason: "Subsequent event", details: {} },
      ],
    },
  });
  render(<AssemblyPage id="b1" />);
  await screen.findByRole("heading", { name: /Assembly/ });
  expect(screen.queryByRole("link", { name: "Produce file (zip)" })).not.toBeInTheDocument();
  expect(screen.getByTestId("produce-blocked")).toHaveTextContent("Re-assemble before producing");
  expect(screen.getByRole("button", { name: "Re-assemble after amendments" })).toBeDisabled(); // C-1 unsigned
});

test("a verification failure lists the mismatches", async () => {
  mockApi({
    "GET /api/binders/b1/assembly": assembled,
    "GET /api/binders/b1/verify": {
      ok: false,
      assembly_hash: HASH,
      recomputed_from_recorded_manifest: HASH,
      current_file_hash: "0".repeat(64),
      current_matches_assembled: false,
      checks: [{ item: "attachment benchmark.csv", ok: false, detail: "stored file no longer matches its hash" }],
    },
  });
  render(<AssemblyPage id="b1" />);
  await screen.findByRole("heading", { name: /Assembly/ });
  fireEvent.click(screen.getByRole("button", { name: "Verify hashes" }));
  const result = await screen.findByTestId("verification");
  expect(result).toHaveTextContent("Verification found mismatches.");
  expect(result).toHaveTextContent("attachment benchmark.csv: stored file no longer matches its hash");
  expect(result).toHaveTextContent("re-assemble");
});

test("the not-checked list is absent when everything could be checked", async () => {
  mockApi({ "GET /api/binders/b1/assembly": assemblyFixture({ not_checked: [] }) });
  render(<AssemblyPage id="b1" />);
  await screen.findByRole("heading", { name: /Assembly & retention/ });
  expect(screen.queryByText("Not checked:")).not.toBeInTheDocument();
  expect(screen.queryByTestId("not-checked")).not.toBeInTheDocument();
});


test("after Assemble the screen shows the assembled state at once, even if a reload lags behind the commit", async () => {
  // Reproduces the defect seen on the development servers (D41): the reload right after the
  // action answered the pre-assembly state. The action's own answer must win, and a reload
  // that reports fewer events is ignored.
  let gets = 0;
  const stale = assemblyFixture({ blockers: [] });
  const afterAssemble = assemblyFixture({
    state: "assembled",
    blockers: [],
    assembled_at: "2026-11-01T20:33:12+05:30",
    assembly_hash: "7".repeat(64),
    matches_recorded_manifest: true,
    manifest: { papers: [] },
    events: [{ id: "e1", kind: "assembled", actor: "partner@firm", at: "2026-11-01T20:33:12+05:30", reason: null, details: {} }],
  });
  mockApi({
    "GET /api/binders/b1/assembly": () => {
      gets += 1;
      return gets <= 2 ? stale : afterAssemble; // first load, then one stale reload
    },
    "POST /api/binders/b1/assemble": afterAssemble,
  });
  render(<AssemblyPage id="b1" />);
  const assemble = await screen.findByRole("button", { name: "Assemble" });
  fireEvent.click(assemble);
  await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("assembled"));
  await waitFor(() => expect(gets).toBe(2)); // the stale reload has come back
  expect(screen.getByTestId("state")).toHaveTextContent("assembled");
  expect(screen.getByTestId("hash")).toHaveTextContent("7".repeat(64));
  expect(screen.getByRole("button", { name: "Re-assemble after amendments" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Verify hashes" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Produce file/ })).toBeInTheDocument();
  expect(screen.getAllByTestId("event")[0]).toHaveTextContent("assembled · partner@firm");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("a refused Assemble leaves the state open and shows the refusal", async () => {
  mockApi({
    "GET /api/binders/b1/assembly": assemblyFixture({ blockers: [] }),
    "POST /api/binders/b1/assemble": {
      httpStatus: 409,
      body: { detail: "assembly is blocked by 1 item(s): unsigned_paper D-1: status is reviewed" },
    },
  });
  render(<AssemblyPage id="b1" />);
  fireEvent.click(await screen.findByRole("button", { name: "Assemble" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("blocked by 1 item(s)");
  expect(screen.getByTestId("state")).toHaveTextContent("open");
  expect(screen.queryByTestId("hash")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Assemble" })).toBeEnabled();
});

test("re-assembly after an amendment replaces the hash and extends the trail", async () => {
  const before = assemblyFixture({
    state: "assembled",
    blockers: [],
    assembled_at: "2026-11-01T20:33:12+05:30",
    assembly_hash: "1".repeat(64),
    matches_recorded_manifest: false,
    manifest: { papers: [] },
    events: [
      { id: "e1", kind: "assembled", actor: "partner@firm", at: "2026-11-01T20:33:12+05:30", reason: null, details: {} },
      { id: "e2", kind: "amended", actor: "partner@firm", at: "2026-11-01T20:36:00+05:30", reason: "objective refined", details: {} },
    ],
  });
  const after = {
    ...before,
    assembled_at: "2026-11-01T20:38:03+05:30",
    assembly_hash: "2".repeat(64),
    matches_recorded_manifest: true,
    events: [...before.events, { id: "e3", kind: "assembled", actor: "partner@firm", at: "2026-11-01T20:38:03+05:30", reason: null, details: {} }],
  };
  let posted = false;
  mockApi({
    "GET /api/binders/b1/assembly": () => (posted ? after : before),
    "POST /api/binders/b1/assemble": () => {
      posted = true;
      return after;
    },
  });
  render(<AssemblyPage id="b1" />);
  expect(await screen.findByText(/amendments pending/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Re-assemble after amendments" }));
  await waitFor(() => expect(screen.getByTestId("hash")).toHaveTextContent("2".repeat(64)));
  expect(screen.queryByText(/amendments pending/)).not.toBeInTheDocument();
  expect(screen.getAllByTestId("event").filter((e) => e.textContent?.includes("assembled · partner@firm"))).toHaveLength(2);
  expect(screen.getByTestId("state")).toHaveTextContent("assembled");
});
