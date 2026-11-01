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
  // Spec 3C (D31): the module source that generated the paper; null for a hand-made one.
  generated_by: string | null;
};

// Spec 3C (D31): where a generated paper came from. `payload` is the provenance block exactly
// as the module delivered it: inputs, citations and the source block.
export type Generation = {
  id: string;
  source: string;
  module: string;
  module_version: string | null;
  run_id: string | null;
  generated_at: string;
  received_by: string;
  received_at: string;
  content_hash_at_intake: string;
  spine_figures_check: "verified" | "not_checked" | null;
  // D37: how the delivery's run was verified at intake (the WorkMind run read back), or null.
  run_verification: Record<string, unknown> | null;
  locked_fields: string[];
  payload: Record<string, unknown>;
  // Stage E (D32): for a paper the Financial Spine produced, whether it still matches the
  // binder's linked version; null for every other source.
  freshness: Freshness | null;
};

export type FreshnessState = "current" | "stale" | "not_checked";
export type Freshness = {
  state: FreshnessState;
  detail: string | null;
  recorded_version_id: string | null;
  recorded_version_label: string | null;
};

// Stage E: the Spine papers of a binder, per area and the adjustment chain (screen 1).
export type SpinePaperState = "none" | FreshnessState;
export type SpineAreaStatus = {
  code: string;
  name: string;
  mapped: boolean;
  listed_heads: string[];
  paper_id: string | null;
  ref: string;
  state: SpinePaperState;
  detail: string | null;
  recorded_version_id: string | null;
  recorded_version_label: string | null;
};
export type SpineChainStatus = {
  ref: string;
  section: string;
  paper_id: string | null;
  state: SpinePaperState;
  can_generate: boolean;
  reason: string | null;
  detail: string | null;
  recorded_version_id: string | null;
  recorded_version_label: string | null;
};
export type SpinePapersStatus = {
  can_generate: boolean;
  reason: string | null;
  version_id: string | null;
  version_label: string | null;
  version_hash: string | null;
  areas: SpineAreaStatus[];
  chain: SpineChainStatus;
  map_problems: string[];
  unassigned_heads: string[];
  // D38: the template's own map, one derived from the Spine's tree, or none.
  map_source: "template" | "derived" | "none";
  beyond_letters: string[];
};
export type ReferenceChanges = { added: string[]; removed: string[]; kept: string[]; for_review: string[] };
export type RegeneratedPaper = Paper & {
  regeneration: { references: ReferenceChanges; previous_run_id: string | null; run_id: string | null };
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
  vault_doc_id: string;
  identifying_chars: string | null;
  attached_by: string;
  attached_at: string;
};

export type BinderState = "open" | "assembled" | "purged";

// Spec 3B, 3E, 4: xref · from_wp · to_wp | to_fs_line | to_vault_doc · direction, read from one
// paper: `outgoing` says whether that paper refers out. `broken` names a target that is gone;
// `checked` is false for an FS line, which cannot be followed without the Spine (D21).
export type Xref = {
  id: string;
  from_wp: string;
  from_ref: string;
  to_wp: string | null;
  to_ref: string | null;
  to_fs_line: string | null;
  to_fs_line_label: string | null;
  to_vault_doc: string | null;
  to_filename: string | null;
  to_attachment_id: string | null;
  to_attachment_ref: string | null;
  direction: "to" | "from";
  outgoing: boolean;
  created_by: string;
  created_at: string;
  broken: string | null;
  checked: boolean;
  // Spec 3E "superseded" (D36): the target paper's content changed since the reference was
  // made or last confirmed; blocks assembly until confirmed or removed.
  target_amended: string | null;
  confirmed_by: string | null;
  confirmed_at: string | null;
  confirmed_version: number | null;
};

export type FsLine = {
  head_id: string;
  label: string;
  side: string | null;
  depth: number | null;
  item: string | null;
  current: string | null;
  prior: string | null;
  has_figures: boolean;
};

export type FsLines = { available: boolean; reason: string | null; version_locked: boolean; lines: FsLine[] };

// Screen 4: FS line → lead schedule → working paper → source document (D30).
export type MapLink = { xref_id: string; direction: "to" | "from"; broken: string | null; amended: string | null; checked: boolean };
export type MapDocument = {
  xref_id: string;
  doc_id: string;
  attachment_id: string | null;
  filename: string | null;
  filed_on_ref: string | null;
  broken: string | null;
};
export type MapPaper = {
  id: string;
  ref: string;
  title: string;
  section: string;
  status: string;
  role: "lead_schedule" | "working_paper";
  link: MapLink | null;
  documents: MapDocument[];
  papers: MapPaper[];
};
export type MapLine = {
  head_id: string;
  label: string | null;
  side: string | null;
  current: string | null;
  prior: string | null;
  known: boolean;
  papers: MapPaper[];
};
export type XrefMap = {
  available: boolean;
  reason: string | null;
  lines: MapLine[];
  beyond_depth: MapPaper[];
  unattached: MapPaper[];
  max_depth: number;
  broken: number;
  amended: number;
  unchecked: number;
  total_references: number;
};

export type XrefCreate = {
  to_wp: string | null;
  to_fs_line: string | null;
  to_vault_doc: string | null;
  direction: "to" | "from";
};

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
  xrefs: Xref[];
  generated: Generation | null;
  // Spec 3D (D33): preparer, the binder's review levels in order, sign-off.
  review_chain: ReviewChain | null;
};

export type ReviewStep = {
  level: string;
  kind: "preparer" | "review" | "sign_off";
  done: boolean;
  by: string | null;
  at: string | null;
  version: number | null;
};
export type ReviewChain = {
  configured: string[];
  steps: ReviewStep[];
  next_level: string | null;
  pending_levels: string[];
  frozen: boolean;
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

// Spec 4: discussion binder · date · participants[] · matter · outcome, append-only.
export type Discussion = {
  id: string;
  binder_id: string;
  date: string;
  participants: string[];
  matter: string;
  outcome: string | null;
  recorded_by: string;
  recorded_at: string;
};

// Spec 4: departure binder · requirement · reason · alternative_procedure · approved_by.
export type Departure = {
  id: string;
  binder_id: string;
  requirement: string;
  reason: string;
  alternative_procedure: string;
  approved_by: string | null;
  recorded_by: string;
  recorded_at: string;
};

export type BinderEvent = {
  id: string;
  kind: "assembled" | "amended" | "purged" | "produced";
  actor: string;
  at: string;
  reason: string | null;
  details: Record<string, unknown>;
};

// Spec 3H: who opened the file after assembly. Empty for an open binder.
export type AccessEntry = { user: string; action: string; at: string };

export type AssemblyStatus = {
  state: BinderState;
  report_date: string | null;
  assembly_due: string | null;
  days_to_assembly: number | null;
  assembled_at: string | null;
  assembly_hash: string | null;
  retention_until: string | null;
  purge_allowed: boolean;
  matches_recorded_manifest: boolean;
  blockers: Blocker[];
  not_checked: string[];
  manifest: {
    papers: { ref: string; title: string; version: number | null; content_hash: string | null; attachments: { filename: string; sha256: string }[] }[];
    spine?: { engagement_id: string; version_id: string | null } | null;
  } | null;
  events: BinderEvent[];
  access: AccessEntry[];
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
  spine_engagement_id: string | null;
  spine_version_id: string | null;
  // Spec 3D (D33): the review levels after the preparer; null means the Pass 1 chain.
  review_levels: string[] | null;
};

// The Financial Spine link (D29): what the binder ties to and what the Spine says now.
export type SpineVersion = {
  version_id: string;
  engagement_id: string;
  version_no: number | null;
  label: string;
  is_locked: boolean;
  locked_by: string | null;
  locked_at: string | null;
  hash: string | null;
  performance_materiality: string | null;
  pm_source: string | null;
  adjustments: Record<string, number> | null;
};

export type SpineLink = {
  configured: boolean;
  engagement_id: string | null;
  version_id: string | null;
  reachable: boolean;
  reason: string | null;
  engagement: { id: string; entity_id: string | null; financial_year_end: string | null; label: string } | null;
  version: SpineVersion | null;
};

export type Binder = BinderSummary & {
  template_label: string;
  days_to_assembly: number | null;
  missing_required: number;
  sections: SectionIndex[];
  review_levels_frozen: boolean;
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
  getSpineLink: (id: string) => request<SpineLink>("GET", `/api/binders/${id}/spine`),
  setSpineLink: (id: string, link: { spine_engagement_id: string | null; spine_version_id: string | null }) =>
    request<Binder>("PATCH", `/api/binders/${id}`, link),
  listSpineVersions: (engagementId: string) =>
    request<SpineVersion[]>("GET", `/api/spine/engagements/${engagementId}/versions`),
  setReviewLevels: (binderId: string, levels: string[] | null) =>
    request<Binder>("PATCH", `/api/binders/${binderId}`, { review_levels: levels }),
  getSpinePapers: (binderId: string) => request<SpinePapersStatus>("GET", `/api/binders/${binderId}/spine-papers`),
  generateLeadSchedules: (binderId: string, areas: string[] | null) =>
    request<Paper[]>("POST", `/api/binders/${binderId}/spine-papers/lead-schedules`, { areas }),
  generateAdjustmentChain: (binderId: string) =>
    request<Paper>("POST", `/api/binders/${binderId}/spine-papers/adjustment-chain`),
  regeneratePaper: (paperId: string) => request<RegeneratedPaper>("POST", `/api/papers/${paperId}/regenerate`),
  createPaper: (
    binderId: string,
    paper: { ref: string; section: string; title: string; sa_refs?: string[] },
  ) =>
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
  addXref: (paperId: string, body: XrefCreate) => request<Paper>("POST", `/api/papers/${paperId}/xrefs`, body),
  removeXref: (id: string) => request<null>("DELETE", `/api/xrefs/${id}`),
  confirmXref: (id: string) => request<Paper>("POST", `/api/xrefs/${id}/confirm`),
  getFsLines: (binderId: string) => request<FsLines>("GET", `/api/binders/${binderId}/fs-lines`),
  getXrefMap: (binderId: string) => request<XrefMap>("GET", `/api/binders/${binderId}/xref-map`),
  listDiscussions: (binderId: string) => request<Discussion[]>("GET", `/api/binders/${binderId}/discussions`),
  recordDiscussion: (
    binderId: string,
    body: { date: string; participants: string[]; matter: string; outcome: string | null; amendment_reason?: string },
  ) => request<Discussion>("POST", `/api/binders/${binderId}/discussions`, body),
  listDepartures: (binderId: string) => request<Departure[]>("GET", `/api/binders/${binderId}/departures`),
  recordDeparture: (
    binderId: string,
    body: {
      requirement: string;
      reason: string;
      alternative_procedure: string;
      approved_by: string | null;
      amendment_reason?: string;
    },
  ) => request<Departure>("POST", `/api/binders/${binderId}/departures`, body),
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
  broken_reference: "Broken cross-reference",
  spine_version_unlocked: "Spine version not locked",
  spine_unreachable: "Financial Spine unreachable",
  spine_version_missing: "Spine version missing",
  spine_version_not_verified: "Spine version not verified",
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
