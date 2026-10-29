// Typed client for the Binder API. Display only: every rule lives in the backend, and the
// shapes here mirror backend/src/oak_binder/schemas.

export type Status = "draft" | "prepared" | "in_review" | "reviewed" | "signed_off";

export type RequiredPaper = { ref: string; section: string; title: string; sa_refs: string[] };

export type TemplateSection = { code: string; name: string };

export type Template = {
  name: string;
  label: string;
  status: string;
  draft: boolean;
  placeholders: string[];
  sections: TemplateSection[];
  required: RequiredPaper[];
};

export type PaperSummary = {
  id: string;
  ref: string;
  section: string;
  title: string;
  status: Status;
  current_version: number | null;
};

export type Version = {
  version: number;
  body: Record<string, unknown>;
  prepared_by: string;
  prepared_at: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  signed_off_by: string | null;
  signed_off_at: string | null;
  content_hash: string;
  amendment_reason: string | null;
};

export type BinderSummaryState = BinderState;

export type Attachment = {
  id: string;
  wp_id: string;
  wp_version_id: string | null;
  filename: string;
  media_type: string;
  size_bytes: number;
  sha256: string;
  identifying_chars: string | null;
  attached_by: string;
  attached_at: string;
};

export type BinderState = "open" | "assembled" | "purged";

export type Paper = PaperSummary & {
  binder_id: string;
  binder_state: BinderState;
  open_review_notes: number;
  sa_refs: string[];
  objective: string | null;
  procedure: string | null;
  population_sample: string | null;
  result: string | null;
  conclusion: string | null;
  created_at: string;
  versions: Version[];
  attachments: Attachment[];
};

export type NoteState = "raised" | "assigned" | "responded" | "cleared";

export type NoteStep = {
  step: number;
  state: NoteState;
  text: string | null;
  assigned_to: string | null;
  actor: string;
  at: string;
};

export type ReviewNote = {
  note_id: string;
  wp_id: string;
  state: NoteState;
  open: boolean;
  text: string;
  raised_by: string;
  raised_at: string;
  assigned_to: string | null;
  response: string | null;
  responded_at: string | null;
  cleared_by: string | null;
  cleared_at: string | null;
  steps: NoteStep[];
};

export type BinderReviewNote = ReviewNote & { ref: string; title: string; paper_status: Status };

export type Blocker = { kind: string; ref: string | null; detail: string };

export type BinderEvent = {
  id: string;
  kind: "assembled" | "amended" | "purged" | "produced";
  actor: string;
  at: string;
  reason: string | null;
  details: Record<string, unknown>;
};

export type AssemblyStatus = {
  state: BinderState;
  report_date: string | null;
  assembly_due: string | null;
  days_to_assembly: number | null;
  assembled_at: string | null;
  assembly_hash: string | null;
  retention_until: string | null;
  purge_allowed: boolean;
  blockers: Blocker[];
  not_checked: string[];
  manifest: { papers: { ref: string; title: string; version: number | null; content_hash: string | null; attachments: { filename: string; sha256: string }[] }[] } | null;
  events: BinderEvent[];
};

export type Verification = {
  ok: boolean;
  assembly_hash: string | null;
  recomputed_from_recorded_manifest: string | null;
  current_file_hash: string;
  current_matches_assembled: boolean;
  checks: { item: string; ok: boolean; detail: string }[];
};

export type PaperContent = Pick<
  Paper,
  | "section"
  | "title"
  | "sa_refs"
  | "objective"
  | "procedure"
  | "population_sample"
  | "result"
  | "conclusion"
>;

export type SectionIndex = {
  code: string;
  name: string;
  papers: PaperSummary[];
  missing: RequiredPaper[];
};

export type BinderSummary = {
  id: string;
  engagement: string;
  template: string;
  report_date: string | null;
  assembly_due: string | null;
  retention_until: string | null;
  assembled_at: string | null;
  assembly_hash: string | null;
  state: BinderState;
  created_at: string;
};

export type Binder = BinderSummary & {
  template_label: string;
  days_to_assembly: number | null;
  missing_required: number;
  sections: SectionIndex[];
};

export type PaperAction = "prepare" | "submit" | "review" | "sign-off";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    detail: string,
  ) {
    super(detail);
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const form = body instanceof FormData;
  const response = await fetch(path, {
    method,
    headers: body === undefined || form ? {} : { "content-type": "application/json" },
    body: body === undefined ? undefined : form ? body : JSON.stringify(body),
  });
  const text = await response.text();
  const data: unknown = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const detail =
      data && typeof data === "object" && "detail" in data
        ? formatDetail((data as { detail: unknown }).detail)
        : response.statusText;
    throw new ApiError(response.status, detail);
  }
  return data as T;
}

function formatDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        const item = d as { loc?: unknown[]; msg?: string };
        return `${(item.loc ?? []).slice(1).join(".")}: ${item.msg ?? "invalid"}`;
      })
      .join("; ");
  }
  return JSON.stringify(detail);
}

export const api = {
  listTemplates: () => request<Template[]>("GET", "/api/templates"),
  listBinders: () => request<BinderSummary[]>("GET", "/api/binders"),
  createBinder: (engagement: string, template: string, report_date: string | null) =>
    request<Binder>("POST", "/api/binders", { engagement, template, report_date }),
  getBinder: (id: string) => request<Binder>("GET", `/api/binders/${id}`),
  setReportDate: (id: string, report_date: string | null) =>
    request<Binder>("PATCH", `/api/binders/${id}`, { report_date }),
  createPaper: (binderId: string, paper: { ref: string; section: string; title: string }) =>
    request<Paper>("POST", `/api/binders/${binderId}/papers`, paper),
  getPaper: (id: string) => request<Paper>("GET", `/api/papers/${id}`),
  updatePaper: (id: string, changes: Partial<PaperContent> & { amendment_reason?: string }) =>
    request<Paper>("PATCH", `/api/papers/${id}`, changes),
  paperAction: (id: string, action: PaperAction) =>
    request<Paper>("POST", `/api/papers/${id}/${action}`),
  uploadAttachment: (
    paperId: string,
    file: File,
    identifyingChars: string,
    amendmentReason?: string,
  ) => {
    const form = new FormData();
    form.append("file", file, file.name);
    if (identifyingChars.trim()) form.append("identifying_chars", identifyingChars.trim());
    if (amendmentReason?.trim()) form.append("amendment_reason", amendmentReason.trim());
    return request<Paper>("POST", `/api/papers/${paperId}/attachments`, form);
  },
  removeAttachment: (id: string) => request<null>("DELETE", `/api/attachments/${id}`),
  attachmentUrl: (id: string) => `/api/attachments/${id}/content`,
  getAssembly: (binderId: string) => request<AssemblyStatus>("GET", `/api/binders/${binderId}/assembly`),
  assemble: (binderId: string) => request<AssemblyStatus>("POST", `/api/binders/${binderId}/assemble`),
  verify: (binderId: string) => request<Verification>("GET", `/api/binders/${binderId}/verify`),
  produceUrl: (binderId: string) => `/api/binders/${binderId}/produce`,
  purge: (binderId: string) => request<AssemblyStatus>("POST", `/api/binders/${binderId}/purge`),
  listPaperNotes: (paperId: string) => request<ReviewNote[]>("GET", `/api/papers/${paperId}/review-notes`),
  listBinderNotes: (binderId: string) =>
    request<BinderReviewNote[]>("GET", `/api/binders/${binderId}/review-notes`),
  raiseNote: (paperId: string, text: string) =>
    request<ReviewNote>("POST", `/api/papers/${paperId}/review-notes`, { text }),
  assignNote: (noteId: string, assigned_to: string) =>
    request<ReviewNote>("POST", `/api/review-notes/${noteId}/assign`, { assigned_to }),
  respondNote: (noteId: string, text: string) =>
    request<ReviewNote>("POST", `/api/review-notes/${noteId}/respond`, { text }),
  clearNote: (noteId: string) => request<ReviewNote>("POST", `/api/review-notes/${noteId}/clear`),
};

export const NOTE_STATE_LABEL: Record<NoteState, string> = {
  raised: "Raised",
  assigned: "Assigned",
  responded: "Responded",
  cleared: "Cleared",
};

export const BLOCKER_LABEL: Record<string, string> = {
  report_not_dated: "Report not dated",
  missing_required_paper: "Missing required paper",
  unsigned_paper: "Paper not signed off",
  open_review_notes: "Open review notes",
};

export const STATUS_LABEL: Record<Status, string> = {
  draft: "Draft",
  prepared: "Prepared",
  in_review: "In review",
  reviewed: "Reviewed",
  signed_off: "Signed off",
};

// The next step in the chain draft -> prepared -> in review -> reviewed -> signed off.
export const NEXT_ACTION: Record<Status, { action: PaperAction; label: string } | null> = {
  draft: { action: "prepare", label: "Prepare" },
  prepared: { action: "submit", label: "Submit for review" },
  in_review: { action: "review", label: "Review" },
  reviewed: { action: "sign-off", label: "Sign off" },
  signed_off: null,
};
