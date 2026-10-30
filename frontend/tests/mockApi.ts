// A fetch stub keyed by "METHOD /path". Each handler returns the JSON body, or an
// { httpStatus, body } pair for an error response. Records every call for assertions.
import { vi } from "vitest";

import type { AssemblyStatus, Binder, Paper, ReviewNote, Version } from "../src/api";

type Handler = (body: unknown) => unknown | Promise<unknown>;
type Routes = Record<string, unknown | Handler>;

export type Call = { method: string; path: string; body: unknown };

export function mockApi(routes: Routes): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      const body = typeof init?.body === "string" ? JSON.parse(init.body) : undefined;
      calls.push({ method, path, body });
      const key = `${method} ${path}`;
      if (!(key in routes)) {
        return new Response(JSON.stringify({ detail: `no mock for ${key}` }), { status: 404 });
      }
      const handler = routes[key];
      // Await async handlers so a test can hold a request open and observe in-flight state.
      const result = typeof handler === "function" ? await (handler as Handler)(body) : handler;
      const response = result as { httpStatus?: number; body?: unknown };
      if (response && typeof response === "object" && "httpStatus" in response) {
        return new Response(JSON.stringify(response.body), { status: response.httpStatus });
      }
      return new Response(JSON.stringify(result), { status: 200 });
    }),
  );
  return calls;
}

export const version1: Version = {
  version: 1,
  body: { title: "Cash and bank", conclusion: "Fairly stated" },
  prepared_by: "preparer@firm",
  prepared_at: "2026-10-28T10:00:00Z",
  reviewed_by: null,
  reviewed_at: null,
  signed_off_by: null,
  signed_off_at: null,
  content_hash: "a".repeat(64),
  amendment_reason: null,
};

export function paperFixture(overrides: Partial<Paper> = {}): Paper {
  return {
    id: "p1",
    binder_id: "b1",
    ref: "D-1",
    section: "D",
    title: "Cash and bank",
    status: "draft",
    current_version: null,
    sa_refs: ["SA 500"],
    objective: "Existence of cash",
    procedure: "Bank confirmations",
    population_sample: "All 4 accounts",
    result: "No exceptions",
    conclusion: "Fairly stated",
    created_at: "2026-10-28T09:00:00Z",
    binder_state: "open",
    open_review_notes: 0,
    versions: [],
    attachments: [],
    ...overrides,
  };
}

export function noteFixture(overrides: Partial<ReviewNote> = {}): ReviewNote {
  return {
    note_id: "n1",
    wp_id: "p1",
    state: "raised",
    open: true,
    text: "Tie the balance to the bank statement",
    raised_by: "reviewer@firm",
    raised_at: "2026-10-29T10:00:00Z",
    assigned_to: null,
    response: null,
    responded_at: null,
    cleared_by: null,
    cleared_at: null,
    steps: [{ step: 1, state: "raised", text: "Tie the balance to the bank statement", assigned_to: null, actor: "reviewer@firm", at: "2026-10-29T10:00:00Z" }],
    ...overrides,
  };
}

export function assemblyFixture(overrides: Partial<AssemblyStatus> = {}): AssemblyStatus {
  return {
    state: "open",
    report_date: "2026-09-30",
    assembly_due: "2026-11-29",
    days_to_assembly: 32,
    assembled_at: null,
    assembly_hash: null,
    retention_until: "2033-09-30",
    purge_allowed: false,
    matches_recorded_manifest: false,
    blockers: [
      { kind: "missing_required_paper", ref: "A-1", detail: "Acceptance and continuance" },
      { kind: "unsigned_paper", ref: "C-1", detail: "status is in_review" },
    ],
    not_checked: [
      "broken cross-references: cross-references are Pass 2 (D21); references to Spine lines and vault documents do not exist yet, so none can be checked",
    ],
    manifest: null,
    events: [],
    ...overrides,
  };
}

export function binderFixture(overrides: Partial<Binder> = {}): Binder {
  return {
    id: "b1",
    engagement: "ENG-2026-001",
    template: "statutory",
    template_label: "Statutory audit",
    report_date: "2026-09-30",
    assembly_due: "2026-11-29",
    retention_until: "2033-09-30",
    assembled_at: null,
    assembly_hash: null,
    state: "open",
    created_at: "2026-10-28T09:00:00Z",
    days_to_assembly: 32,
    missing_required: 5,
    sections: [
      { code: "A", name: "Acceptance", papers: [], missing: [{ ref: "A-1", section: "A", title: "Acceptance and continuance", sa_refs: ["SA 210"] }] },
      { code: "B", name: "Planning and risk", papers: [], missing: [] },
      {
        code: "C",
        name: "Materiality",
        papers: [{ id: "p-c1", ref: "C-1", section: "C", title: "Materiality memo", status: "signed_off", current_version: 2 }],
        missing: [],
      },
      {
        code: "D",
        name: "Financial statement area D",
        papers: [{ id: "p1", ref: "D-1", section: "D", title: "Cash and bank", status: "in_review", current_version: 1 }],
        missing: [],
      },
    ],
    ...overrides,
  };
}
