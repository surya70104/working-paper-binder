import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import type { Departure, Discussion } from "../src/api";
import { BinderPage } from "../src/pages/BinderPage";
import { SPINE_PAPERS_NONE, SPINE_UNCONFIGURED, binderFixture, mockApi } from "./mockApi";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const discussion: Discussion = {
  id: "d1",
  binder_id: "b1",
  date: "2026-10-30",
  participants: ["A. Partner", "R. Mehta (TCWG, Audit Committee Chair)"],
  matter: "Going concern: covenant breach at year end",
  outcome: "Management to provide a 12-month cash-flow forecast",
  recorded_by: "partner@firm",
  recorded_at: "2026-10-30T10:00:00Z",
};

const departure: Departure = {
  id: "x1",
  binder_id: "b1",
  requirement: "SA 505 external confirmation of bank balances",
  reason: "The bank did not respond within the reporting timetable",
  alternative_procedure: "Agreed closing balances to statements and subsequent receipts",
  approved_by: null,
  recorded_by: "manager@firm",
  recorded_at: "2026-10-29T15:00:00Z",
};

test("the binder screen lists both logs with participants, outcome and approval state", async () => {
  mockApi({
    "GET /api/binders/b1": binderFixture(),
    "GET /api/binders/b1/discussions": [discussion],
    "GET /api/binders/b1/departures": [departure],
    "GET /api/binders/b1/spine-papers": SPINE_PAPERS_NONE, "GET /api/binders/b1/spine": SPINE_UNCONFIGURED,
  });
  render(<BinderPage id="b1" />);
  await screen.findByRole("heading", { name: "Discussions" });
  const row = await screen.findByTestId("discussion");
  expect(row).toHaveTextContent("2026-10-30 · A. Partner; R. Mehta (TCWG, Audit Committee Chair)");
  expect(row).toHaveTextContent("Outcome: Management to provide a 12-month cash-flow forecast");
  expect(row).toHaveTextContent("recorded by partner@firm");
  const dep = screen.getByTestId("departure");
  expect(dep).toHaveTextContent("SA 505 external confirmation of bank balances");
  expect(dep).toHaveTextContent("Alternative procedure: Agreed closing balances");
  expect(dep).toHaveTextContent("not yet approved");
  expect(screen.getByRole("button", { name: "Record discussion" })).toBeEnabled();
  expect(screen.queryByTestId("records-amendment-reason")).not.toBeInTheDocument();
});

test("recording a discussion splits participants by line and reloads the list", async () => {
  let recorded = false;
  const calls = mockApi({
    "GET /api/binders/b1": binderFixture(),
    "GET /api/binders/b1/discussions": () => (recorded ? [discussion] : []),
    "GET /api/binders/b1/departures": [],
    "GET /api/binders/b1/spine-papers": SPINE_PAPERS_NONE, "GET /api/binders/b1/spine": SPINE_UNCONFIGURED,
    "POST /api/binders/b1/discussions": () => {
      recorded = true;
      return discussion;
    },
  });
  render(<BinderPage id="b1" />);
  await screen.findByText("No discussions recorded.");
  fireEvent.change(screen.getByLabelText("Date"), { target: { value: "2026-10-30" } });
  fireEvent.change(screen.getByLabelText("Participants"), {
    target: { value: "A. Partner\nR. Mehta (TCWG, Audit Committee Chair)\n" },
  });
  fireEvent.change(screen.getByLabelText("Matter"), {
    target: { value: "Going concern: covenant breach at year end" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Record discussion" }));
  await waitFor(() => expect(screen.getByTestId("discussion")).toBeInTheDocument());
  const post = calls.find((c) => c.method === "POST");
  expect(post?.body).toEqual({
    date: "2026-10-30",
    participants: ["A. Partner", "R. Mehta (TCWG, Audit Committee Chair)"],
    matter: "Going concern: covenant breach at year end",
    outcome: null,
  });
});

test("after assembly an entry needs an amendment reason, and a purged binder takes none", async () => {
  const calls = mockApi({
    "GET /api/binders/b1": binderFixture({ state: "assembled" }),
    "GET /api/binders/b1/discussions": [],
    "GET /api/binders/b1/departures": [],
    "GET /api/binders/b1/spine-papers": SPINE_PAPERS_NONE, "GET /api/binders/b1/spine": SPINE_UNCONFIGURED,
    "POST /api/binders/b1/departures": departure,
  });
  render(<BinderPage id="b1" />);
  await screen.findByRole("heading", { name: "Departures" });
  const record = screen.getByRole("button", { name: "Record departure as amendment" });
  expect(record).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Requirement departed from"), { target: { value: "SA 505" } });
  fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "No reply" } });
  fireEvent.change(screen.getByLabelText("Alternative procedure performed"), {
    target: { value: "Agreed to statements" },
  });
  expect(record).toBeDisabled(); // still: no amendment reason
  fireEvent.change(screen.getByTestId("records-amendment-reason"), {
    target: { value: "Approval recorded after the report date" },
  });
  expect(record).toBeEnabled();
  fireEvent.click(record);
  await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
  expect(calls.find((c) => c.method === "POST")?.body).toEqual({
    requirement: "SA 505",
    reason: "No reply",
    alternative_procedure: "Agreed to statements",
    approved_by: null,
    amendment_reason: "Approval recorded after the report date",
  });
  cleanup();

  mockApi({
    "GET /api/binders/b1": binderFixture({ state: "purged" }),
    "GET /api/binders/b1/discussions": [],
    "GET /api/binders/b1/departures": [],
    "GET /api/binders/b1/spine-papers": SPINE_PAPERS_NONE, "GET /api/binders/b1/spine": SPINE_UNCONFIGURED,
  });
  render(<BinderPage id="b1" />);
  await screen.findByRole("heading", { name: "Departures" });
  expect(screen.queryByRole("button", { name: /Record departure/ })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Record discussion/ })).not.toBeInTheDocument();
});
