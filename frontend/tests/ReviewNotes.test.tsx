import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { PaperPage } from "../src/pages/PaperPage";
import { ReviewNotesPage } from "../src/pages/ReviewNotesPage";
import { mockApi, noteFixture, paperFixture, version1 } from "./mockApi";

afterEach(() => vi.unstubAllGlobals());

const reviewed = paperFixture({ status: "reviewed", current_version: 2, versions: [version1] });

test("an open note blocks sign-off on the paper screen and says so", async () => {
  mockApi({
    "GET /api/papers/p1": { ...reviewed, open_review_notes: 1 },
    "GET /api/papers/p1/review-notes": [noteFixture()],
  });
  render(<PaperPage id="p1" />);
  await screen.findByRole("heading", { name: /D-1/ });
  expect(screen.getByRole("button", { name: "Sign off" })).toBeDisabled();
  expect(screen.getByText(/1 open review note: a paper with an open review note cannot be signed off/)).toBeInTheDocument();
  expect(screen.getByTestId("open-notes")).toHaveTextContent("1 open");
  expect(screen.getAllByTestId("note")).toHaveLength(1);
  expect(screen.getByRole("button", { name: "Assign" })).toBeDisabled(); // no assignee typed yet
});

test("each note offers only its next step: assign, respond, clear", async () => {
  let note = noteFixture();
  const calls = mockApi({
    "GET /api/papers/p1": () => ({ ...reviewed, open_review_notes: note.open ? 1 : 0 }),
    "GET /api/papers/p1/review-notes": () => [note],
    "POST /api/review-notes/n1/assign": (body: unknown) => {
      note = { ...note, state: "assigned", assigned_to: (body as { assigned_to: string }).assigned_to };
      return note;
    },
    "POST /api/review-notes/n1/respond": (body: unknown) => {
      note = { ...note, state: "responded", response: (body as { text: string }).text, responded_at: "2026-10-29T11:00:00Z" };
      return note;
    },
    "POST /api/review-notes/n1/clear": () => {
      note = { ...note, state: "cleared", open: false, cleared_by: "reviewer@firm", cleared_at: "2026-10-29T12:00:00Z" };
      return note;
    },
  });
  render(<PaperPage id="p1" />);
  await screen.findByRole("heading", { name: /D-1/ });

  fireEvent.change(screen.getByLabelText("Assign to"), { target: { value: "preparer@firm" } });
  fireEvent.click(screen.getByRole("button", { name: "Assign" }));
  await screen.findByText(/assigned to preparer@firm/);
  expect(calls.find((c) => c.path.endsWith("/assign"))?.body).toEqual({ assigned_to: "preparer@firm" });

  fireEvent.change(screen.getByLabelText("Response"), { target: { value: "Reconciled" } });
  fireEvent.click(screen.getByRole("button", { name: "Respond" }));
  await screen.findByText(/Reconciled/);
  expect(screen.getByRole("button", { name: "Sign off" })).toBeDisabled(); // responded still blocks

  fireEvent.click(screen.getByRole("button", { name: "Clear" }));
  await waitFor(() => expect(screen.getByTestId("open-notes")).toHaveTextContent("none open"));
  expect(screen.getByText(/cleared by reviewer@firm/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Sign off" })).toBeEnabled();
  expect(screen.queryByRole("button", { name: "Clear" })).not.toBeInTheDocument();
});

test("raising a note posts its text", async () => {
  const calls = mockApi({
    "GET /api/papers/p1": reviewed,
    "GET /api/papers/p1/review-notes": [],
    "POST /api/papers/p1/review-notes": (body: unknown) => noteFixture({ text: (body as { text: string }).text }),
  });
  render(<PaperPage id="p1" />);
  await screen.findByRole("heading", { name: /D-1/ });
  expect(screen.getByRole("button", { name: "Raise note" })).toBeDisabled();
  fireEvent.change(screen.getByLabelText("New review note"), { target: { value: "Cut-off not tested" } });
  fireEvent.click(screen.getByRole("button", { name: "Raise note" }));
  await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
  expect(calls.find((c) => c.method === "POST")?.body).toEqual({ text: "Cut-off not tested" });
});

test("screen 3 lists what is open, who raised it, who holds it, and what it blocks", async () => {
  mockApi({
    "GET /api/binders/b1/review-notes": [
      { ...noteFixture(), ref: "D-1", title: "Cash and bank", paper_status: "in_review", assigned_to: "preparer@firm", state: "assigned" },
      { ...noteFixture({ note_id: "n2", wp_id: "p2", state: "cleared", open: false, cleared_by: "reviewer@firm" }), ref: "D-2", title: "Receivables", paper_status: "signed_off" },
    ],
  });
  render(<ReviewNotesPage id="b1" />);
  await screen.findByRole("heading", { name: "Review notes" });
  expect(screen.getByTestId("summary")).toHaveTextContent("1 open review note on 1 paper");
  let rows = screen.getAllByTestId("note-row");
  expect(rows).toHaveLength(1);
  expect(rows[0]).toHaveTextContent("D-1");
  expect(rows[0]).toHaveTextContent("Assigned");
  expect(rows[0]).toHaveTextContent("preparer@firm");
  expect(rows[0]).toHaveTextContent("sign-off of D-1 (In review) and assembly");

  fireEvent.click(screen.getByLabelText("Show cleared notes"));
  rows = screen.getAllByTestId("note-row");
  expect(rows).toHaveLength(2);
  expect(rows[1]).toHaveTextContent("nothing");
});
