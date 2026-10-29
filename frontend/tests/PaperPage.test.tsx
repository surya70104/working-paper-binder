import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { PaperPage } from "../src/pages/PaperPage";
import { mockApi, paperFixture, version1 } from "./mockApi";

afterEach(() => vi.unstubAllGlobals());

test("a draft paper opens in Edit mode, offers Prepare, and shows its fields", async () => {
  mockApi({ "GET /api/papers/p1/review-notes": [], "GET /api/papers/p1": paperFixture() });
  render(<PaperPage id="p1" />);
  expect(await screen.findByRole("heading", { name: /D-1 Cash and bank/ })).toBeInTheDocument();
  expect(screen.getByTestId("status")).toHaveTextContent("Draft");
  expect(screen.getByRole("button", { name: "Prepare" })).toBeEnabled();
  expect(screen.getByRole("button", { name: "Edit" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByLabelText("Conclusion")).toHaveValue("Fairly stated");
  expect(screen.getByText(/No versions yet/)).toBeInTheDocument();
});

test("a paper under review opens in Read mode with rendered, sanitised markdown", async () => {
  mockApi({
    "GET /api/papers/p1/review-notes": [],
    "GET /api/papers/p1": paperFixture({
      status: "in_review",
      current_version: 1,
      versions: [version1],
      conclusion: "Cash is **fairly stated**.\n\n- no exceptions <script>alert(1)</script>",
    }),
  });
  render(<PaperPage id="p1" />);
  await screen.findByRole("heading", { name: /D-1/ });
  expect(screen.getByRole("button", { name: "Read" })).toHaveAttribute("aria-pressed", "true");
  const conclusion = screen.getByTestId("read-conclusion");
  expect(conclusion.querySelector("strong")).toHaveTextContent("fairly stated");
  expect(conclusion.querySelector("li")).toHaveTextContent("no exceptions");
  expect(document.querySelector("script")).toBeNull();
  expect(conclusion).not.toHaveTextContent("alert(1)");
  // The textareas are hidden in Read mode and come back in Edit mode.
  expect(screen.getByLabelText("Conclusion")).not.toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Edit" }));
  expect(screen.getByLabelText("Conclusion")).toBeVisible();
  expect(screen.queryByTestId("read-conclusion")).not.toBeInTheDocument();
});

test("sign-off is blocked without a conclusion (SA 230)", async () => {
  mockApi({
    "GET /api/papers/p1/review-notes": [],
    "GET /api/papers/p1": paperFixture({
      status: "reviewed",
      conclusion: null,
      current_version: 2,
      versions: [version1, { ...version1, version: 2, reviewed_by: "reviewer@firm", reviewed_at: "2026-10-28T11:00:00Z" }],
    }),
  });
  render(<PaperPage id="p1" />);
  await screen.findByRole("heading", { name: /D-1/ });
  expect(screen.getByRole("button", { name: "Sign off" })).toBeDisabled();
  expect(screen.getByText(/cannot be signed off/)).toBeInTheDocument();
});

test("sign-off posts the action once the conclusion is saved", async () => {
  const reviewed = paperFixture({ status: "reviewed", current_version: 2, versions: [version1] });
  const calls = mockApi({
    "GET /api/papers/p1/review-notes": [],
    "GET /api/papers/p1": reviewed,
    "POST /api/papers/p1/sign-off": { ...reviewed, status: "signed_off" },
  });
  render(<PaperPage id="p1" />);
  await screen.findByRole("heading", { name: /D-1/ });
  const button = screen.getByRole("button", { name: "Sign off" });
  expect(button).toBeEnabled();
  fireEvent.click(button);
  await waitFor(() =>
    expect(calls.some((c) => c.method === "POST" && c.path === "/api/papers/p1/sign-off")).toBe(
      true,
    ),
  );
});

test("unsaved edits disable the workflow until saved, and save sends only the changes", async () => {
  const draft = paperFixture();
  const calls = mockApi({
    "GET /api/papers/p1/review-notes": [],
    "GET /api/papers/p1": draft,
    "PATCH /api/papers/p1": (body: unknown) => ({ ...draft, ...(body as object) }),
  });
  render(<PaperPage id="p1" />);
  await screen.findByRole("heading", { name: /D-1/ });

  fireEvent.change(screen.getByLabelText("Result"), {
    target: { value: "No exceptions after follow-up" },
  });
  expect(screen.getByRole("button", { name: "Prepare" })).toBeDisabled();
  expect(screen.getByText("Save your changes first.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(calls.some((c) => c.method === "PATCH")).toBe(true));
  const patch = calls.find((c) => c.method === "PATCH");
  expect(patch?.body).toEqual({ result: "No exceptions after follow-up" });
});

test("the version history lists preparer, reviewer and signer", async () => {
  const v2 = { ...version1, version: 2, reviewed_by: "reviewer@firm", reviewed_at: "2026-10-28T11:00:00Z" };
  const v3 = { ...v2, version: 3, signed_off_by: "partner@firm", signed_off_at: "2026-10-28T12:00:00Z" };
  mockApi({
    "GET /api/papers/p1/review-notes": [],
    "GET /api/papers/p1": paperFixture({ status: "signed_off", current_version: 3, versions: [version1, v2, v3] }),
  });
  render(<PaperPage id="p1" />);
  await screen.findByRole("heading", { name: /D-1/ });
  expect(screen.getByText("Signed off.")).toBeInTheDocument();
  const rows = screen.getAllByRole("row");
  expect(rows).toHaveLength(4); // header + 3 versions
  expect(rows[1]).not.toHaveTextContent("reviewer@firm");
  expect(rows[2]).toHaveTextContent("reviewer@firm");
  expect(rows[3]).toHaveTextContent("partner@firm");
});

test("attachments are listed with hash and download link, and can be removed before assembly", async () => {
  const attachment = {
    id: "a1",
    wp_id: "p1",
    wp_version_id: null,
    filename: "bank confirmation.pdf",
    media_type: "application/pdf",
    size_bytes: 1234,
    sha256: "9".repeat(64),
    identifying_chars: "HDFC a/c 1234",
    attached_by: "preparer@firm",
    attached_at: "2026-10-28T10:00:00Z",
  };
  const calls = mockApi({
    "GET /api/papers/p1/review-notes": [],
    "GET /api/papers/p1": paperFixture({ attachments: [attachment] }),
    "DELETE /api/attachments/a1": null,
  });
  render(<PaperPage id="p1" />);
  await screen.findByRole("heading", { name: /D-1/ });
  expect(screen.getByRole("link", { name: "bank confirmation.pdf" })).toHaveAttribute(
    "href",
    "/api/attachments/a1/content",
  );
  expect(screen.getByText(/HDFC a\/c 1234/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Remove" }));
  await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
});

test("an assembled binder turns saves and uploads into amendments that need a reason", async () => {
  const calls = mockApi({
    "GET /api/papers/p1/review-notes": [],
    "GET /api/papers/p1": paperFixture({ status: "signed_off", current_version: 3, versions: [version1], binder_state: "assembled" }),
    "PATCH /api/papers/p1": (body: unknown) => paperFixture({ ...(body as object), status: "draft", binder_state: "assembled" }),
  });
  render(<PaperPage id="p1" />);
  await screen.findByRole("heading", { name: /D-1/ });
  expect(screen.getByText(/This file is assembled/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Remove" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Edit" }));
  fireEvent.change(screen.getByLabelText("Conclusion"), { target: { value: "Revised" } });
  const save = screen.getByRole("button", { name: "Save as amendment" });
  expect(save).toBeDisabled(); // no reason yet
  fireEvent.change(screen.getByLabelText(/Amendment reason/), { target: { value: "Subsequent event" } });
  expect(save).toBeEnabled();
  fireEvent.click(save);
  await waitFor(() => expect(calls.some((c) => c.method === "PATCH")).toBe(true));
  expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({
    conclusion: "Revised",
    amendment_reason: "Subsequent event",
  });
});

test("buttons are disabled while a request is in flight", async () => {
  let release: () => void = () => undefined;
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  let current = paperFixture();
  mockApi({
    "GET /api/papers/p1/review-notes": [],
    "GET /api/papers/p1": () => current,
    "POST /api/papers/p1/prepare": async () => {
      await pending;
      current = { ...current, status: "prepared", current_version: 1, versions: [version1] };
      return current;
    },
  });
  render(<PaperPage id="p1" />);
  await screen.findByRole("heading", { name: /D-1/ });

  const prepare = screen.getByRole("button", { name: "Prepare" });
  fireEvent.click(prepare);
  await waitFor(() => expect(prepare).toBeDisabled());
  expect(screen.getByText("Working…")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();

  release();
  await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("Prepared"));
  expect(screen.getByRole("button", { name: "Submit for review" })).toBeEnabled();
});
