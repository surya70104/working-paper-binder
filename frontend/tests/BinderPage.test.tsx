import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { BinderPage, countdownText } from "../src/pages/BinderPage";
import { binderFixture, mockApi } from "./mockApi";

afterEach(() => vi.unstubAllGlobals());

test("the countdown reads the 60-day clock", () => {
  expect(countdownText(binderFixture({ days_to_assembly: 32 }))).toBe(
    "Assembly due 2026-11-29: 32 days left.",
  );
  expect(countdownText(binderFixture({ days_to_assembly: 0 }))).toBe(
    "Assembly is due today, 2026-11-29.",
  );
  expect(countdownText(binderFixture({ days_to_assembly: -3 }))).toBe(
    "Assembly was due 2026-11-29: 3 days overdue.",
  );
  expect(
    countdownText(binderFixture({ report_date: null, assembly_due: null, days_to_assembly: null })),
  ).toMatch(/not yet dated/);
});

test("the binder screen shows the index tree, completeness and the clocks", async () => {
  mockApi({ "GET /api/binders/b1": binderFixture() });
  render(<BinderPage id="b1" />);

  expect(await screen.findByRole("heading", { name: "ENG-2026-001" })).toBeInTheDocument();
  expect(screen.getByText("Assembly due 2026-11-29: 32 days left.")).toBeInTheDocument();
  expect(screen.getByText(/Retain until 2033-09-30/)).toBeInTheDocument();
  expect(screen.getByText(/Missing required papers:/)).toHaveTextContent("5");

  const sectionC = screen.getByRole("heading", { name: "C · Materiality" }).parentElement!;
  expect(within(sectionC).getByRole("link", { name: /C-1 Materiality memo/ })).toHaveAttribute(
    "href",
    "#/papers/p-c1",
  );
  expect(within(sectionC).getByText("Signed off")).toBeInTheDocument();

  const sectionA = screen.getByRole("heading", { name: "A · Acceptance" }).parentElement!;
  expect(within(sectionA).getByText(/Acceptance and continuance — missing/)).toBeInTheDocument();

  // Section B has neither papers nor missing papers, so it is not drawn.
  expect(screen.queryByRole("heading", { name: "B · Planning and risk" })).not.toBeInTheDocument();
});

test("a missing required paper pre-fills the new paper form", async () => {
  mockApi({ "GET /api/binders/b1": binderFixture() });
  render(<BinderPage id="b1" />);
  await screen.findByRole("heading", { name: "ENG-2026-001" });

  fireEvent.click(screen.getByRole("button", { name: "Create" }));
  expect(screen.getByLabelText(/Reference/)).toHaveValue("A-1");
  expect(screen.getByLabelText("Section")).toHaveValue("A");
  expect(screen.getByLabelText("Title")).toHaveValue("Acceptance and continuance");
});

test("an assembled binder is read-only", async () => {
  mockApi({
    "GET /api/binders/b1": binderFixture({
      state: "assembled",
      assembled_at: "2026-11-01T00:00:00Z",
      assembly_hash: "f".repeat(64),
    }),
  });
  render(<BinderPage id="b1" />);
  await screen.findByRole("heading", { name: "ENG-2026-001" });
  expect(screen.getByRole("button", { name: "Create paper" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Set" })).toBeDisabled();
});
