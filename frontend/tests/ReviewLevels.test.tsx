import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import type { ReviewChain } from "../src/api";
import { ReviewLevelsCard } from "../src/components/ReviewLevelsCard";
import { PaperPage } from "../src/pages/PaperPage";
import { binderFixture, mockApi, paperFixture } from "./mockApi";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const chain: ReviewChain = {
  configured: ["senior", "manager", "partner"],
  steps: [
    { level: "preparer", kind: "preparer", done: true, by: "preparer@firm", at: "2026-10-28T10:00:00Z", version: 1 },
    { level: "senior", kind: "review", done: true, by: "senior@firm", at: "2026-10-29T09:00:00Z", version: 1 },
    { level: "manager", kind: "review", done: false, by: null, at: null, version: null },
    { level: "partner", kind: "review", done: false, by: null, at: null, version: null },
    { level: "sign-off", kind: "sign_off", done: false, by: null, at: null, version: null },
  ],
  next_level: "manager",
  pending_levels: ["manager", "partner"],
  frozen: true,
};

test("the paper screen lists the chain with the preparer first and names the next level on the action", async () => {
  mockApi({
    "GET /api/papers/p1/review-notes": [],
    "GET /api/papers/p1": paperFixture({ status: "in_review", current_version: 1, review_chain: chain }),
  });
  render(<PaperPage id="p1" />);
  await screen.findByRole("heading", { name: /D-1/ });
  const steps = screen.getAllByTestId("review-step");
  expect(steps).toHaveLength(5);
  expect(steps.map((s) => within(s).getByTestId("review-step-state").textContent)).toEqual([
    "done",
    "done",
    "pending",
    "pending",
    "pending",
  ]);
  expect(steps[0]).toHaveTextContent("preparer");
  expect(steps[0]).toHaveTextContent("preparer@firm");
  expect(steps[0]).toHaveTextContent("version 1");
  expect(steps[1]).toHaveTextContent("senior@firm");
  expect(steps[2]).toHaveTextContent("manager");
  expect(steps[2]).toHaveTextContent("next");
  expect(steps[3]).toHaveTextContent("partner");
  expect(steps[3]).not.toHaveTextContent("next");
  expect(steps[4]).toHaveTextContent("sign-off");
  expect(screen.getByRole("button", { name: "Review as manager" })).toBeEnabled();
  expect(screen.getByText(/Review levels: preparer → senior → manager → partner → sign-off/)).toBeInTheDocument();
});

test("a binder without levels shows the Pass 1 chain and the plain Review action", async () => {
  const pass1: ReviewChain = {
    configured: [],
    steps: [
      { level: "preparer", kind: "preparer", done: true, by: "preparer@firm", at: "2026-10-28T10:00:00Z", version: 1 },
      { level: "review", kind: "review", done: false, by: null, at: null, version: null },
      { level: "sign-off", kind: "sign_off", done: false, by: null, at: null, version: null },
    ],
    next_level: "review",
    pending_levels: [],
    frozen: false,
  };
  mockApi({
    "GET /api/papers/p1/review-notes": [],
    "GET /api/papers/p1": paperFixture({ status: "in_review", current_version: 1, review_chain: pass1 }),
  });
  render(<PaperPage id="p1" />);
  await screen.findByRole("heading", { name: /D-1/ });
  expect(screen.getAllByTestId("review-step")).toHaveLength(3);
  expect(screen.getByRole("button", { name: "Review" })).toBeEnabled();
  expect(screen.queryByText(/Review levels:/)).not.toBeInTheDocument();
});

test("the levels card is editable on an open binder before any review and saves the list", async () => {
  const onChanged = vi.fn(async () => undefined);
  const calls = mockApi({ "PATCH /api/binders/b1": binderFixture({ review_levels: ["senior", "partner"] }) });
  render(<ReviewLevelsCard binder={binderFixture()} onChanged={onChanged} />);
  expect(screen.getByTestId("review-levels-default")).toHaveTextContent("no levels configured");
  const input = screen.getByLabelText(/Review levels after the preparer/);
  fireEvent.change(input, { target: { value: " senior, partner " } });
  fireEvent.click(screen.getByRole("button", { name: "Save review levels" }));
  await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
  expect(calls.filter((c) => c.method === "PATCH")[0]?.body).toEqual({ review_levels: ["senior", "partner"] });
});

test("clearing the list sends null, and a refusal is shown as said", async () => {
  mockApi({
    "PATCH /api/binders/b1": {
      httpStatus: 409,
      body: { detail: "the review levels are frozen: a level review has been recorded on a paper of this binder" },
    },
  });
  render(<ReviewLevelsCard binder={binderFixture({ review_levels: ["senior"] })} onChanged={async () => undefined} />);
  fireEvent.change(screen.getByLabelText(/Review levels after the preparer/), { target: { value: "" } });
  fireEvent.click(screen.getByRole("button", { name: "Save review levels" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("review levels are frozen");
});

test("a frozen or assembled binder shows the chain read-only", async () => {
  mockApi({});
  render(<ReviewLevelsCard binder={binderFixture({ review_levels: ["senior", "partner"], review_levels_frozen: true })} onChanged={async () => undefined} />);
  const card = screen.getByTestId("review-levels-card");
  expect(card).toHaveTextContent("preparer → senior → partner → sign-off");
  expect(screen.getByTestId("review-levels-frozen")).toHaveTextContent("Frozen: a level review has been recorded");
  expect(within(card).queryByRole("button")).not.toBeInTheDocument();
  cleanup();
  render(<ReviewLevelsCard binder={binderFixture({ state: "assembled", review_levels: null })} onChanged={async () => undefined} />);
  expect(screen.getByTestId("review-levels-frozen")).toHaveTextContent("The binder is assembled");
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});
