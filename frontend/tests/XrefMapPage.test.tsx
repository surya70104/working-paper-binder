import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import type { XrefMap } from "../src/api";
import { XrefMapPage } from "../src/pages/XrefMapPage";
import { mockApi } from "./mockApi";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const map: XrefMap = {
  available: true,
  reason: null,
  total_references: 4,
  broken: 1,
  amended: 1,
  unchecked: 0,
  lines: [
    {
      head_id: "BS.A.1",
      label: "Cash and cash equivalents",
      side: "assets",
      current: "1250000.00",
      prior: null,
      known: true,
      papers: [
        {
          id: "p-lead",
          ref: "D-L",
          title: "Cash lead schedule",
          section: "D",
          status: "signed_off",
          role: "lead_schedule",
          link: { xref_id: "x1", direction: "to", broken: null, amended: null, checked: true },
          documents: [],
          papers: [
            {
              id: "p1",
              ref: "D-1",
              title: "Cash and bank",
              section: "D",
              status: "in_review",
              role: "working_paper",
              link: {
                xref_id: "x2",
                direction: "to",
                broken: null,
                amended: "paper D-L has been amended since this reference was made (version 3 → 4)",
                checked: true,
              },
              documents: [
                {
                  xref_id: "x3",
                  doc_id: "a".repeat(64),
                  attachment_id: "att-1",
                  filename: "statement.pdf",
                  filed_on_ref: "D-1",
                  broken: null,
                },
                {
                  xref_id: "x4",
                  doc_id: "b".repeat(64),
                  attachment_id: null,
                  filename: null,
                  filed_on_ref: null,
                  broken: "no paper of this binder carries that document any more",
                },
              ],
              papers: [],
            },
          ],
        },
      ],
    },
  ],
  beyond_depth: [
    {
      id: "p4",
      ref: "D-4",
      title: "Four levels down",
      section: "D",
      status: "draft",
      role: "working_paper",
      link: { xref_id: "x9", direction: "to", broken: null, amended: null, checked: true },
      documents: [],
      papers: [],
    },
  ],
  unattached: [
    {
      id: "p9",
      ref: "E-1",
      title: "Not tied to anything",
      section: "E",
      status: "draft",
      role: "working_paper",
      link: null,
      documents: [],
      papers: [],
    },
  ],
  max_depth: 3,
};

test("the map shows FS line → lead schedule → working paper → source document with flags", async () => {
  mockApi({ "GET /api/binders/b1/xref-map": map });
  render(<XrefMapPage id="b1" />);
  await screen.findByRole("heading", { name: "Cross-reference map" });
  expect(screen.getByTestId("map-summary")).toHaveTextContent("4 reference(s) · 1 broken · 1 with an amended target · 0 not checked");
  const line = screen.getByTestId("map-line");
  expect(line).toHaveTextContent("Cash and cash equivalents");
  expect(line).toHaveTextContent("BS.A.1");
  expect(line).toHaveTextContent("₹1250000.00");
  const lead = within(line).getByTestId("map-lead");
  expect(within(lead).getByRole("link", { name: "D-L" })).toHaveAttribute("href", "#/papers/p-lead");
  const paper = within(lead).getByTestId("map-paper");
  expect(within(paper).getByRole("link", { name: "D-1" })).toHaveAttribute("href", "#/papers/p1");
  expect(within(paper).getByTestId("map-amended")).toHaveTextContent("amended since this reference was made (version 3 → 4)");
  const docs = within(paper).getAllByTestId("map-document");
  expect(docs).toHaveLength(2);
  expect(within(docs[0]!).getByRole("link", { name: "statement.pdf" })).toHaveAttribute("href", "/api/attachments/att-1/content");
  expect(within(docs[1]!).getByTestId("map-broken")).toHaveTextContent("broken: no paper of this binder carries that document any more");
  // A paper deeper than the three drawn levels is still part of the chain: listed as such,
  // never among the papers tied to no line.
  const beyond = screen.getByTestId("map-beyond");
  expect(within(beyond).getByRole("heading", { name: "Papers further down a chain" })).toBeInTheDocument();
  expect(beyond).toHaveTextContent("deeper than the 3 levels the map draws");
  expect(within(beyond).getByRole("link", { name: "D-4" })).toHaveAttribute("href", "#/papers/p4");
  const unattached = screen.getByRole("heading", { name: "Papers not tied to any financial statement line" });
  expect(unattached).toBeInTheDocument();
  expect(within(unattached.parentElement!).getByRole("link", { name: "E-1" })).toHaveAttribute("href", "#/papers/p9");
  expect(within(unattached.parentElement!).queryByRole("link", { name: "D-4" })).not.toBeInTheDocument();
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
});

test("the further-down section is absent when every chain fits the drawn depth", async () => {
  mockApi({ "GET /api/binders/b1/xref-map": { ...map, beyond_depth: [] } });
  render(<XrefMapPage id="b1" />);
  await screen.findByRole("heading", { name: "Cross-reference map" });
  expect(screen.queryByTestId("map-beyond")).not.toBeInTheDocument();
});

test("without a linked Spine the map says lines are not checked and shows free-text lines", async () => {
  mockApi({
    "GET /api/binders/b1/xref-map": {
      ...map,
      available: false,
      reason: "the binder is not linked to a Financial Spine version",
      broken: 0,
      amended: 0,
      unchecked: 1,
      lines: [{ ...map.lines[0]!, head_id: "Trade receivables", label: null, current: null, known: false, papers: [] }],
      beyond_depth: [],
      unattached: [],
    },
  });
  render(<XrefMapPage id="b1" />);
  await screen.findByRole("heading", { name: "Cross-reference map" });
  expect(screen.getByRole("status")).toHaveTextContent("Financial-statement lines cannot be checked: the binder is not linked");
  expect(screen.getByTestId("map-line")).toHaveTextContent("Trade receivables");
  expect(screen.getByTestId("map-line")).toHaveTextContent("not checked");
  expect(screen.getByText("Every paper is reachable from a financial statement line.")).toBeInTheDocument();
});
