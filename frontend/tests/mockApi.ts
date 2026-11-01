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
    generated_by: null,
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
    xrefs: [],
    generated: null,
    review_chain: null,
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
      "cross-references to FS lines: the binder is not linked to a Financial Spine version (D29, D30), so a reference to an FS line cannot be followed; references to papers and documents are checked (none in this file)",
    ],
    manifest: null,
    events: [],
    access: [],
    ...overrides,
  };
}

// Stage E: no Spine papers and nothing to generate, as an unlinked binder answers.
export const SPINE_PAPERS_NONE = {
  can_generate: false,
  reason: "the binder is not linked to a Financial Spine version (D29)",
  version_id: null,
  version_label: null,
  version_hash: null,
  areas: [],
  chain: {
    ref: "W-ADJ",
    section: "W",
    paper_id: null,
    state: "none",
    can_generate: false,
    reason: "the binder is not linked to a Financial Spine version (D29)",
    detail: null,
    recorded_version_id: null,
    recorded_version_label: null,
  },
  map_problems: [],
  unassigned_heads: [],
  map_source: "none",
  beyond_letters: [],
};

export const SPINE_UNCONFIGURED = {
  configured: false,
  engagement_id: null,
  version_id: null,
  reachable: false,
  reason: null,
  engagement: null,
  version: null,
};

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
    spine_engagement_id: null,
    spine_version_id: null,
    review_levels: null,
    review_levels_frozen: false,
    days_to_assembly: 32,
    missing_required: 5,
    sections: [
      { code: "A", name: "Acceptance", papers: [], missing: [{ ref: "A-1", section: "A", title: "Acceptance and continuance", sa_refs: ["SA 210"] }] },
      { code: "B", name: "Planning and risk", papers: [], missing: [] },
      {
        code: "C",
        name: "Materiality",
        papers: [{ id: "p-c1", ref: "C-1", section: "C", title: "Materiality memo", status: "signed_off", current_version: 2, generated_by: null }],
        missing: [],
      },
      {
        code: "D",
        name: "Financial statement area D",
        papers: [{ id: "p1", ref: "D-1", section: "D", title: "Cash and bank", status: "in_review", current_version: 1, generated_by: null }],
        missing: [],
      },
    ],
    ...overrides,
  };
}
