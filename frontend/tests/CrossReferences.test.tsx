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
    "GET /api/papers/p1": paperFixture({ xrefs: [outToBank, inFromLead, fsLine, brokenDoc, linkedDoc] }),
    "GET /api/binders/b1": binderFixture(),
  });
  render(<PaperPage id="p1" />);
  await screen.findByRole("heading", { name: /Cross-references/ });
  expect(screen.getByTestId("xref-summary")).toHaveTextContent("1 broken — blocks assembly");
  const rows = screen.getAllByTestId("xref");
  expect(rows).toHaveLength(5);
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
  expect(rows[4]).toHaveTextContent("D-L → this paper");
  expect(rows[4]?.querySelector("a")).toHaveAttribute("href", "#/papers/p3");
  // Only references written on this paper can be removed from here.
  expect(screen.getAllByRole("button", { name: "Remove" })).toHaveLength(4);
});

test("adding a reference to another paper posts one target and reloads the paper", async () => {
  const binder = binderFixture();
  const calls = mockApi({
    "GET /api/papers/p1/review-notes": [],
    "GET /api/papers/p1": () => paperFixture({ xrefs: calls.some((c) => c.method === "POST") ? [outToBank] : [] }),
    "GET /api/binders/b1": binder,
    "POST /api/papers/p1/xrefs": paperFixture({ xrefs: [outToBank] }),
  });
  render(<PaperPage id="p1" />);
  await screen.findByRole("heading", { name: /Cross-references/ });
  expect(screen.getByTestId("xref-summary")).toHaveTextContent("0 out, 0 in");
  const add = screen.getByRole("button", { name: "Add reference" });
  expect(add).toBeDisabled();
  const picker = await screen.findByTestId("xref-paper");
  await waitFor(() => expect(picker.querySelectorAll("option").length).toBeGreaterThan(1));
  // The paper itself is not offered as a target.
  expect(Array.from(picker.querySelectorAll("option")).map((o) => o.getAttribute("value"))).not.toContain("p1");
  const other = binder.sections.flatMap((s) => s.papers).find((p) => p.id !== "p1");
  fireEvent.change(picker, { target: { value: other?.id } });
  fireEvent.change(screen.getByLabelText("Direction"), { target: { value: "from" } });
  expect(add).toBeEnabled();
  fireEvent.click(add);
  await waitFor(() => expect(screen.getByTestId("xref-summary")).toHaveTextContent("1 out, 0 in"));
  const post = calls.find((c) => c.method === "POST");
  expect(post?.path).toBe("/api/papers/p1/xrefs");
  expect(post?.body).toEqual({ to_wp: other?.id, to_fs_line: null, to_vault_doc: null, direction: "from" });
});

test("an FS line is typed, a document comes from this paper's attachments, nothing is editable after assembly", async () => {
  const calls = mockApi({
    "GET /api/papers/p1/review-notes": [],
    "GET /api/papers/p1": paperFixture({
      attachments: [
        {
          id: "a1",
          wp_id: "p1",
          wp_version_id: null,
          filename: "statement.pdf",
          media_type: "application/pdf",
          size_bytes: 10,
          sha256: "9".repeat(64),
          vault_doc_id: "9".repeat(64),
          identifying_chars: null,
          attached_by: "preparer@firm",
          attached_at: "2026-10-28T10:00:00Z",
        },
      ],
    }),
    "POST /api/papers/p1/xrefs": paperFixture({ xrefs: [fsLine] }),
  });
  render(<PaperPage id="p1" />);
  await screen.findByRole("heading", { name: /Cross-references/ });
  fireEvent.change(screen.getByLabelText("Target"), { target: { value: "fs_line" } });
  fireEvent.change(screen.getByLabelText(/FS line/), { target: { value: "  Cash and cash equivalents " } });
  fireEvent.click(screen.getByRole("button", { name: "Add reference" }));
  await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
  expect(calls.find((c) => c.method === "POST")?.body).toEqual({
    to_wp: null,
    to_fs_line: "Cash and cash equivalents",
    to_vault_doc: null,
    direction: "to",
  });
  fireEvent.change(screen.getByLabelText("Target"), { target: { value: "document" } });
  const options = Array.from(document.querySelectorAll("#xref-docs option"));
  expect(options.map((o) => o.getAttribute("value"))).toEqual(["9".repeat(64)]);
  expect(options[0]).toHaveTextContent("statement.pdf");
  cleanup();

  mockApi({
    "GET /api/papers/p1/review-notes": [],
    "GET /api/papers/p1": paperFixture({ binder_state: "assembled", status: "signed_off", xrefs: [outToBank] }),
  });
  render(<PaperPage id="p1" />);
  await screen.findByRole("heading", { name: /Cross-references/ });
  expect(screen.queryByRole("button", { name: "Add reference" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Remove" })).not.toBeInTheDocument();
});
