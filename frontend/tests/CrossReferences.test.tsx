import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import type { Xref } from "../src/api";
import { PaperPage } from "../src/pages/PaperPage";
import { binderFixture, mockApi, paperFixture } from "./mockApi";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const outToBank: Xref = {
  id: "x1",
  from_wp: "p1",
  from_ref: "D-1",
  to_wp: "p2",
  to_ref: "D-2",
  to_fs_line: null,
  to_fs_line_label: null,
  to_vault_doc: null,
  to_filename: null,
  to_attachment_id: null,
  to_attachment_ref: null,
  direction: "to",
  outgoing: true,
  created_by: "preparer@firm",
  created_at: "2026-10-30T09:00:00Z",
  broken: null,
  checked: true,
  target_amended: null,
  confirmed_by: null,
  confirmed_at: null,
  confirmed_version: null,
};

const inFromLead: Xref = {
  ...outToBank,
  id: "x2",
  from_wp: "p3",
  from_ref: "D-L",
  to_wp: "p1",
  to_ref: "D-1",
  outgoing: false,
};

const fsLine: Xref = {
  ...outToBank,
  id: "x3",
  to_wp: null,
  to_ref: null,
  to_fs_line: "Cash and cash equivalents",
  checked: false,
};

const linkedDoc: Xref = {
  ...outToBank,
  id: "x5",
  to_wp: null,
  to_ref: null,
  to_vault_doc: "b".repeat(64),
  to_filename: "statement.pdf",
  to_attachment_id: "a9",
  to_attachment_ref: "D-2",
};

const amendedTarget: Xref = {
  ...outToBank,
  id: "x6",
  to_wp: "p4",
  to_ref: "D-4",
  target_amended: "paper D-4 has been amended since this reference was made (version 2 → 3)",
};

const brokenDoc: Xref = {
  ...outToBank,
  id: "x4",
  to_wp: null,
  to_ref: null,
  to_vault_doc: "a".repeat(64),
  broken: "no paper of this binder carries that document any more",
};

test("references are listed in and out, with broken and unchecked ones marked", async () => {
  mockApi({
    "GET /api/papers/p1/review-notes": [],
    "GET /api/papers/p1": paperFixture({ xrefs: [outToBank, inFromLead, fsLine, brokenDoc, linkedDoc, amendedTarget] }),
    "GET /api/binders/b1": binderFixture(),
  });
  render(<PaperPage id="p1" />);
  await screen.findByRole("heading", { name: /Cross-references/ });
  expect(screen.getByTestId("xref-summary")).toHaveTextContent("2 broken — blocks assembly");
  const rows = screen.getAllByTestId("xref");
  expect(rows).toHaveLength(6);
  expect(rows[0]).toHaveTextContent("this paper → D-2");
  expect(rows[0]?.querySelector("a")).toHaveAttribute("href", "#/papers/p2");
  expect(rows[1]).toHaveTextContent("this paper → FS line “Cash and cash equivalents”");
  expect(rows[1]).toHaveTextContent("not checked (no Spine)");
  expect(rows[2]).toHaveTextContent("this paper → document");
  expect(screen.getByTestId("xref-broken")).toHaveTextContent(
    "broken: no paper of this binder carries that document any more",
  );
  // A document target is clickable: it links to the attachment it is filed as.
  expect(rows[3]).toHaveTextContent("this paper → document statement.pdf (filed on D-2)");
  expect(screen.getByRole("link", { name: "statement.pdf" })).toHaveAttribute(
    "href",
    "/api/attachments/a9/content",
  );
  // The incoming one is read from this paper: D-L refers to it.
  // Outgoing rows come first (five of them); the incoming one follows.
  expect(rows[4]).toHaveTextContent("this paper → D-4");
  expect(rows[5]).toHaveTextContent("D-L → this paper");
  expect(rows[5]?.querySelector("a")).toHaveAttribute("href", "#/papers/p3");
  // A superseded target (spec 3E; D36) is shown on the row and counts as blocking.
  expect(screen.getByTestId("xref-amended")).toHaveTextContent(
    "superseded: paper D-4 has been amended since this reference was made (version 2 → 3)",
  );
  expect(screen.getByTestId("xref-summary")).toHaveTextContent("2 broken — blocks assembly");
  // Only references written on this paper can be removed from here; only the superseded one
  // offers Confirm.
  expect(screen.getAllByRole("button", { name: "Remove" })).toHaveLength(5);
  expect(screen.getAllByRole("button", { name: "Confirm" })).toHaveLength(1);
});

test("confirming a superseded reference posts to its confirm action", async () => {
  const calls = mockApi({
    "GET /api/papers/p1/review-notes": [],
    "GET /api/papers/p1": paperFixture({ xrefs: [amendedTarget] }),
    "GET /api/binders/b1": binderFixture(),
    "POST /api/xrefs/x6/confirm": paperFixture({ xrefs: [amendedTarget] }),
  });
  render(<PaperPage id="p1" />);
  await screen.findByRole("heading", { name: /Cross-references/ });
  expect(screen.getByTestId("xref-summary")).toHaveTextContent("1 broken — blocks assembly");
  fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
  await waitFor(() => expect(calls.filter((c) => c.method === "POST")).toHaveLength(1));
  expect(calls.filter((c) => c.method === "POST")[0]?.path).toBe("/api/xrefs/x6/confirm");
});

test("a confirmed reference shows who confirmed it and no longer counts as blocking", async () => {
  const confirmed: Xref = {
    ...amendedTarget,
    target_amended: null,
    confirmed_by: "reviewer@firm",
    confirmed_at: "2026-11-01T10:00:00Z",
    confirmed_version: 3,
  };
  mockApi({
    "GET /api/papers/p1/review-notes": [],
    "GET /api/papers/p1": paperFixture({ xrefs: [confirmed] }),
    "GET /api/binders/b1": binderFixture(),
  });
  render(<PaperPage id="p1" />);
  await screen.findByRole("heading", { name: /Cross-references/ });
  expect(screen.getByTestId("xref-confirmed")).toHaveTextContent("confirmed against version 3 by reviewer@firm");
  expect(screen.queryByTestId("xref-amended")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Confirm" })).not.toBeInTheDocument();
  expect(screen.getByTestId("xref-summary")).toHaveTextContent("1 out, 0 in");
});
