// Stale-state regression tests: rapid repeated clicks, and a failed action against a
// record the backend had already moved on. Exercised through the real screens.
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { AssemblyPage } from "../src/pages/AssemblyPage";
import { BinderPage } from "../src/pages/BinderPage";
import { PaperPage } from "../src/pages/PaperPage";
import { assemblyFixture, binderFixture, mockApi, paperFixture, version1 } from "./mockApi";

afterEach(() => vi.unstubAllGlobals());

function gate() {
  let release: () => void = () => undefined;
  const promise = new Promise<void>((resolve) => {
    release = resolve;
  });
  return { promise, release: () => release() };
}

const inReview = paperFixture({ status: "in_review", current_version: 4, versions: [version1] });
const reviewed = paperFixture({
  status: "reviewed",
  current_version: 5,
  versions: [version1, { ...version1, version: 5, reviewed_by: "dev@localhost", reviewed_at: "2026-10-29T11:38:33Z" }],
});

test("rapid repeated clicks send one request, and buttons stay disabled until the reload finishes", async () => {
  const post = gate();
  const get = gate();
  let current = inReview;
  let reloads = 0;
  const calls = mockApi({
    "GET /api/papers/p1/review-notes": [],
    "GET /api/papers/p1": async () => {
      reloads += 1;
      if (reloads > 1) await get.promise; // hold the reload that follows the action
      return current;
    },
    "POST /api/papers/p1/review": async () => {
      await post.promise;
      current = reviewed;
      return current;
    },
  });
  render(<PaperPage id="p1" />);
  const review = await screen.findByRole("button", { name: "Review" });

  fireEvent.click(review);
  fireEvent.click(review);
  fireEvent.click(review);
  await waitFor(() => expect(review).toBeDisabled());
  expect(calls.filter((c) => c.method === "POST")).toHaveLength(1);

  post.release(); // the backend answers; the reload is now in flight and still held
  await waitFor(() => expect(reloads).toBe(2));
  expect(screen.getByText("Working…")).toBeInTheDocument();
  expect(screen.getByTestId("status")).toHaveTextContent("In review"); // old data, but no button
  expect(screen.queryByRole("button", { name: "Review" })).toBeDisabled();

  get.release(); // the reload lands: new status, new button
  await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("Reviewed"));
  expect(screen.getByRole("button", { name: "Sign off" })).toBeEnabled();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(calls.filter((c) => c.method === "POST")).toHaveLength(1);
});

test("a failed action against stale data shows the refusal and the real current state", async () => {
  let reloads = 0;
  mockApi({
    "GET /api/papers/p1/review-notes": [],
    "GET /api/papers/p1": () => {
      reloads += 1;
      return reloads === 1 ? inReview : reviewed; // the backend had already moved on
    },
    "POST /api/papers/p1/review": {
      httpStatus: 409,
      body: { detail: "cannot review paper C-1: its status is reviewed, not in_review" },
    },
  });
  render(<PaperPage id="p1" />);
  fireEvent.click(await screen.findByRole("button", { name: "Review" }));

  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent("its status is reviewed, not in_review");
  await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("Reviewed"));
  expect(screen.getByText(/version 5/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Sign off" })).toBeEnabled();
  expect(screen.queryByRole("button", { name: "Review" })).not.toBeInTheDocument();
});

test("a successful action clears an earlier error", async () => {
  let current = inReview;
  let attempts = 0;
  mockApi({
    "GET /api/papers/p1/review-notes": [],
    "GET /api/papers/p1": () => current,
    "POST /api/papers/p1/review": () => {
      attempts += 1;
      if (attempts === 1) return { httpStatus: 503, body: { detail: "No identity is configured" } };
      current = reviewed;
      return current;
    },
  });
  render(<PaperPage id="p1" />);
  fireEvent.click(await screen.findByRole("button", { name: "Review" }));
  await screen.findByRole("alert");
  await waitFor(() => expect(screen.getByRole("button", { name: "Review" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "Review" }));
  await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("Reviewed"));
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("the binder page reloads after a refused report date and keeps the real value", async () => {
  mockApi({
    "GET /api/binders/b1": binderFixture({ report_date: "2026-09-30" }),
    "PATCH /api/binders/b1": {
      httpStatus: 409,
      body: { detail: "binder for 'ENG-2026-001' is assembled" },
    },
  });
  render(<BinderPage id="b1" />);
  await screen.findByRole("heading", { name: "ENG-2026-001" });
  fireEvent.change(screen.getByLabelText("Report date"), { target: { value: "2026-10-01" } });
  fireEvent.click(screen.getByRole("button", { name: "Set" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("is assembled");
  await waitFor(() => expect(screen.getByLabelText("Report date")).toHaveValue("2026-09-30"));
  expect(screen.getByRole("button", { name: "Set" })).toBeEnabled();
});

test("the assembly page reloads blockers after a refused assemble", async () => {
  let reloads = 0;
  mockApi({
    "GET /api/binders/b1/assembly": () => {
      reloads += 1;
      return reloads === 1
        ? assemblyFixture({ blockers: [] }) // the page thinks nothing blocks
        : assemblyFixture(); // the backend knows better
    },
    "POST /api/binders/b1/assemble": {
      httpStatus: 409,
      body: { detail: "assembly is blocked by 2 item(s): missing_required_paper A-1; unsigned_paper C-1" },
    },
  });
  render(<AssemblyPage id="b1" />);
  const assemble = await screen.findByRole("button", { name: "Assemble" });
  expect(assemble).toBeEnabled();
  fireEvent.click(assemble);
  expect(await screen.findByRole("alert")).toHaveTextContent("blocked by 2 item(s)");
  await waitFor(() => expect(screen.getByTestId("blockers")).toHaveTextContent("A-1"));
  expect(screen.getByRole("button", { name: "Assemble" })).toBeDisabled();
});
