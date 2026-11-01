import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { BindersPage } from "../src/pages/BindersPage";
import { binderFixture, mockApi } from "./mockApi";

afterEach(() => vi.unstubAllGlobals());

const templates = [
  {
    name: "statutory",
    label: "Statutory audit",
    status: "draft: for chartered accountant review",
    draft: true,
    placeholders: ["financial statement areas D-T (17) carry generic names", "marked draft"],
    sections: [],
    required: [],
  },
  { name: "tax_audit", label: "Tax audit", status: "approved", draft: false, placeholders: [], sections: [], required: [] },
];

test("a draft template shows its placeholders on the creation form", async () => {
  mockApi({ "GET /api/binders": [], "GET /api/templates": templates });
  render(<BindersPage />);
  await screen.findByText("No binders yet.");
  const warning = await screen.findByTestId("template-draft");
  expect(warning).toHaveTextContent("This index template is a draft: for chartered accountant review");
  expect(warning).not.toHaveTextContent("draft: draft:");
  expect(warning).toHaveTextContent("financial statement areas D-T (17) carry generic names");
  fireEvent.change(screen.getByLabelText("Index template"), { target: { value: "tax_audit" } });
  expect(screen.queryByTestId("template-draft")).not.toBeInTheDocument();
});

test("the binder list links to each binder and shows its state", async () => {
  mockApi({
    "GET /api/binders": [
      binderFixture(),
      binderFixture({ id: "b2", engagement: "ENG-2026-002", template: "tax_audit", report_date: null }),
    ],
    "GET /api/templates": templates,
  });
  render(<BindersPage />);
  const first = await screen.findByRole("link", { name: "ENG-2026-001" });
  expect(first).toHaveAttribute("href", "#/binders/b1");
  expect(screen.getByText(/statutory · open · report dated 2026-09-30/)).toBeInTheDocument();
  expect(screen.getByText(/tax audit · open$/)).toBeInTheDocument();
  expect(screen.getByRole("option", { name: "Tax audit" })).toBeInTheDocument();
});

test("creating a binder posts the form and navigates to it", async () => {
  const calls = mockApi({
    "GET /api/binders": [],
    "GET /api/templates": templates,
    "POST /api/binders": (body: unknown) => binderFixture({ id: "b9", ...(body as object) }),
  });
  window.location.hash = "#/";
  render(<BindersPage />);
  await screen.findByText("No binders yet.");

  fireEvent.change(screen.getByLabelText("Engagement"), { target: { value: "ENG-2026-009" } });
  fireEvent.change(screen.getByLabelText("Index template"), { target: { value: "tax_audit" } });
  fireEvent.change(screen.getByLabelText(/Report date/), { target: { value: "2026-10-28" } });
  fireEvent.click(screen.getByRole("button", { name: "Create binder" }));

  await waitFor(() => expect(window.location.hash).toBe("#/binders/b9"));
  const post = calls.find((c) => c.method === "POST");
  expect(post?.body).toEqual({
    engagement: "ENG-2026-009",
    template: "tax_audit",
    report_date: "2026-10-28",
  });
});

test("a refused creation shows the backend's reason", async () => {
  mockApi({
    "GET /api/binders": [],
    "GET /api/templates": templates,
    "POST /api/binders": { httpStatus: 409, body: { detail: "a binder already exists for engagement 'ENG-1'" } },
  });
  render(<BindersPage />);
  await screen.findByText("No binders yet.");
  fireEvent.change(screen.getByLabelText("Engagement"), { target: { value: "ENG-1" } });
  fireEvent.click(screen.getByRole("button", { name: "Create binder" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("already exists");
});
