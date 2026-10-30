import { useCallback, useEffect, useState } from "react";

import { api, NEXT_ACTION, STATUS_LABEL, type Paper, type PaperContent, type ReviewNote } from "../api";
import { CrossReferences } from "../components/CrossReferences";
import { ReviewNotes } from "../components/ReviewNotes";
import { Markdown } from "../markdown";
import { href } from "../router";
import { useAction } from "../useAction";

type Form = {
  title: string;
  section: string;
  sa_refs: string;
  objective: string;
  procedure: string;
  population_sample: string;
  result: string;
  conclusion: string;
};

const SECTIONS = [..."ABCDEFGHIJKLMNOPQRST", "W", "X", "Z"];

// The five long fields, in the order the specification gives them (spec 2, 3B).
type LongField = "objective" | "procedure" | "population_sample" | "result" | "conclusion";
const LONG_FIELDS: { key: LongField; label: string; rows: number }[] = [
  { key: "objective", label: "Objective", rows: 3 },
  { key: "procedure", label: "Procedure performed", rows: 3 },
  { key: "population_sample", label: "Population and sample", rows: 2 },
  { key: "result", label: "Result", rows: 3 },
  { key: "conclusion", label: "Conclusion", rows: 3 },
];

function toForm(p: Paper): Form {
  return {
    title: p.title,
    section: p.section,
    sa_refs: p.sa_refs.join(", "),
    objective: p.objective ?? "",
    procedure: p.procedure ?? "",
    population_sample: p.population_sample ?? "",
    result: p.result ?? "",
    conclusion: p.conclusion ?? "",
  };
}

function toChanges(form: Form, paper: Paper): Partial<PaperContent> {
  const changes: Partial<PaperContent> = {};
  if (form.title !== paper.title) changes.title = form.title;
  if (form.section !== paper.section) changes.section = form.section;
  const refs = form.sa_refs
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  if (refs.join("|") !== paper.sa_refs.join("|")) changes.sa_refs = refs;
  for (const key of ["objective", "procedure", "population_sample", "result", "conclusion"] as const) {
    const value = form[key].trim() || null;
    if (value !== paper[key]) changes[key] = value;
  }
  return changes;
}

function who(name: string | null, at: string | null) {
  if (!name) return "—";
  return (
    <>
      {name} <span className="text-slate-500">{at}</span>
    </>
  );
}

export function PaperPage({ id }: { id: string }) {
  const [paper, setPaper] = useState<Paper | null>(null);
  const [notes, setNotes] = useState<ReviewNote[]>([]);
  const [form, setForm] = useState<Form | null>(null);
  // "read" shows the long fields as rendered markdown; "edit" shows the textareas. A paper
  // opens in read mode once it has left draft, since that is when it is being reviewed.
  const [mode, setMode] = useState<"read" | "edit" | null>(null);
  const [reason, setReason] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [identifying, setIdentifying] = useState("");

  // Reload the paper from the backend. The form is rebuilt from what came back, so after
  // an action the fields, status and buttons all describe the same record.
  const load = useCallback(async () => {
    const [p, n] = await Promise.all([api.getPaper(id), api.listPaperNotes(id)]);
    setPaper(p);
    setNotes(n);
    setForm(toForm(p));
    setMode((current) => current ?? (p.status === "draft" ? "edit" : "read"));
  }, [id]);
  const { run, busy, error, setError } = useAction(load);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load, setError]);

  if (error && !paper) {
    return (
      <p role="alert" className="text-red-700">
        {error}
      </p>
    );
  }
  if (!paper || !form) return <p className="text-slate-500">Loading…</p>;

  const changes = toChanges(form, paper);
  const dirty = Object.keys(changes).length > 0;
  const assembled = paper.binder_state === "assembled";
  const purged = paper.binder_state === "purged";
  // After assembly every change is an amendment and needs a reason (spec 3F).
  const needsReason = assembled && reason.trim().length === 0;
  const next = purged ? null : NEXT_ACTION[paper.status];
  const hasConclusion = form.conclusion.trim().length > 0;
  const openNotes = paper.open_review_notes;
  const signOffBlocked = next?.action === "sign-off" && (!hasConclusion || openNotes > 0);
  const reading = mode === "read";
  const field = (key: keyof Form, label: string, rows: number) => (
    <label className="grid gap-1 text-sm">
      {label}
      <textarea
        rows={rows}
        value={form[key]}
        onChange={(e) => setForm({ ...form, [key]: e.target.value })}
        className="rounded border border-slate-300 px-2 py-1 font-sans"
      />
    </label>
  );

  return (
    <div className="space-y-8">
      <section>
        <p className="text-sm text-slate-500">
          <a href="#/" className="hover:underline">
            Binders
          </a>{" "}
          /{" "}
          <a href={href({ name: "binder", id: paper.binder_id })} className="hover:underline">
            Binder
          </a>{" "}
          / {paper.ref}
        </p>
        <h1 className="text-xl font-semibold">
          <span className="font-mono">{paper.ref}</span> {paper.title}
        </h1>
        <p className="text-sm text-slate-600">
          Section {paper.section} · <span data-testid="status">{STATUS_LABEL[paper.status]}</span>
          {paper.current_version !== null ? ` · version ${paper.current_version}` : ""}
        </p>
        {assembled && (
          <p className="mt-2 rounded bg-amber-50 px-3 py-2 text-sm text-amber-900">
            This file is assembled. Any change is an amendment: it needs a reason and writes a
            new version; nothing is deleted.
          </p>
        )}
        {purged && (
          <p className="mt-2 rounded bg-slate-100 px-3 py-2 text-sm text-slate-700">
            This file was purged after retention. Attachments are gone; the versions and their
            hashes remain.
          </p>
        )}
        {error && (
          <p role="alert" className="mt-2 text-sm text-red-700">
            {error}
          </p>
        )}
      </section>

      <section className="rounded border border-slate-200 bg-white p-4">
        <h2 className="text-lg font-semibold">Sign-off</h2>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          {next ? (
            <button
              type="button"
              disabled={busy || dirty || signOffBlocked}
              onClick={() => void run(() => api.paperAction(id, next.action))}
              className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white hover:bg-slate-700 disabled:opacity-50"
            >
              {next.label}
            </button>
          ) : (
            <span className="text-sm text-green-800">Signed off.</span>
          )}
          {busy && <span className="text-sm text-slate-600">Working…</span>}
          {dirty && !busy && <span className="text-sm text-slate-600">Save your changes first.</span>}
          {signOffBlocked && !dirty && !hasConclusion && (
            <span className="text-sm text-amber-900">
              A paper without a conclusion cannot be signed off (SA 230).
            </span>
          )}
          {signOffBlocked && !dirty && hasConclusion && openNotes > 0 && (
            <span className="text-sm text-amber-900">
              {openNotes} open review note{openNotes === 1 ? "" : "s"}: a paper with an open review
              note cannot be signed off (SA 230).
            </span>
          )}
        </div>
        <p className="mt-2 text-xs text-slate-500">
          draft → prepared → in review → reviewed → signed off. Each sign-off writes an
          immutable version; editing returns the paper to draft.
        </p>
      </section>

      <section>
        <div className="flex items-baseline justify-between">
          <h2 className="text-lg font-semibold">Working paper</h2>
          <div className="flex gap-1 text-sm" role="group" aria-label="View">
            <button
              type="button"
              onClick={() => setMode("read")}
              aria-pressed={reading}
              className="rounded border border-slate-300 px-2 py-1 aria-pressed:bg-slate-900 aria-pressed:text-white"
            >
              Read
            </button>
            <button
              type="button"
              onClick={() => setMode("edit")}
              aria-pressed={!reading}
              className="rounded border border-slate-300 px-2 py-1 aria-pressed:bg-slate-900 aria-pressed:text-white"
            >
              Edit
            </button>
          </div>
        </div>

        {reading && (
          <dl className="mt-3 grid gap-4 rounded border border-slate-200 bg-white p-4 text-sm">
            <div>
              <dt className="text-slate-500">SA references</dt>
              <dd>{paper.sa_refs.length ? paper.sa_refs.join(", ") : "—"}</dd>
            </div>
            {LONG_FIELDS.map(({ key, label }) => (
              <div key={key} data-testid={`read-${key}`}>
                <dt className="text-slate-500">{label}</dt>
                <dd>
                  <Markdown text={paper[key] ?? ""} />
                </dd>
              </div>
            ))}
            {dirty && (
              <p className="text-xs text-amber-900">
                Unsaved edits are not shown here. Switch to Edit to save or revise them.
              </p>
            )}
          </dl>
        )}

        <form
          hidden={reading}
          onSubmit={(e) => {
            e.preventDefault();
            void run(() =>
              api.updatePaper(id, assembled ? { ...changes, amendment_reason: reason.trim() } : changes),
            );
          }}
          className="mt-3 grid gap-3"
        >
          {assembled && (
            <label className="grid gap-1 text-sm">
              Amendment reason (required after assembly)
              <input
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                className="rounded border border-amber-300 px-2 py-1"
              />
            </label>
          )}
          <div className="grid gap-3 md:grid-cols-[1fr_auto_1fr]">
            <label className="grid gap-1 text-sm">
              Title
              <input
                value={form.title}
                onChange={(e) => setForm({ ...form, title: e.target.value })}
                className="rounded border border-slate-300 px-2 py-1"
              />
            </label>
            <label className="grid gap-1 text-sm">
              Section
              <select
                value={form.section}
                onChange={(e) => setForm({ ...form, section: e.target.value })}
                className="rounded border border-slate-300 px-2 py-1"
              >
                {SECTIONS.map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </label>
            <label className="grid gap-1 text-sm">
              SA references (comma separated)
              <input
                value={form.sa_refs}
                onChange={(e) => setForm({ ...form, sa_refs: e.target.value })}
                className="rounded border border-slate-300 px-2 py-1"
              />
            </label>
          </div>
          {LONG_FIELDS.map(({ key, label, rows }) => (
            <div key={key}>{field(key, label, rows)}</div>
          ))}
          <p className="text-xs text-slate-500">
            These fields accept markdown: paragraphs, lists, emphasis, links and tables. The
            Read view shows the result.
          </p>
          <button
            type="submit"
            disabled={busy || !dirty || needsReason || purged}
            className="w-fit rounded border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100 disabled:opacity-50"
          >
            {assembled ? "Save as amendment" : "Save"}
          </button>
        </form>
      </section>

      <ReviewNotes paperId={id} notes={notes} busy={busy} run={run} canRaise={!purged} />

      <section>
        <h2 className="text-lg font-semibold">Attachments</h2>
        <p className="text-xs text-slate-500">
          Original files, kept in their native format and identified by SHA-256. Attaching a
          file changes the paper, so it returns to draft until prepared again.
        </p>
        {paper.attachments.length === 0 ? (
          <p className="mt-2 text-sm text-slate-500">{purged ? "Purged." : "No attachments."}</p>
        ) : (
          <ul className="mt-2 divide-y divide-slate-100 rounded border border-slate-200 bg-white text-sm">
            {paper.attachments.map((a) => (
              <li key={a.id} className="flex flex-wrap items-baseline justify-between gap-2 px-3 py-2">
                <span>
                  <a href={api.attachmentUrl(a.id)} className="font-medium underline">
                    {a.filename}
                  </a>{" "}
                  <span className="text-slate-500">
                    {a.size_bytes} bytes · {a.identifying_chars ?? "no identifying characteristics"} ·{" "}
                    {a.attached_by}
                  </span>
                </span>
                <span className="flex items-baseline gap-3">
                  <code className="font-mono text-xs text-slate-500">{a.sha256.slice(0, 16)}…</code>
                  {!assembled && !purged && (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void run(() => api.removeAttachment(a.id))}
                      className="text-xs underline disabled:opacity-50"
                    >
                      Remove
                    </button>
                  )}
                </span>
              </li>
            ))}
          </ul>
        )}
        {!purged && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (!file) return;
              void run(async () => {
                await api.uploadAttachment(id, file, identifying, assembled ? reason : undefined);
                setFile(null);
                setIdentifying("");
              });
            }}
            className="mt-3 grid max-w-xl gap-2 text-sm"
          >
            <label className="grid gap-1">
              File (xlsx, xls, csv, pdf, docx, txt, png, jpg)
              <input
                type="file"
                data-testid="file-input"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                className="text-sm"
              />
            </label>
            <label className="grid gap-1">
              Identifying characteristics of items tested (invoice numbers, voucher refs, dates)
              <input
                value={identifying}
                onChange={(e) => setIdentifying(e.target.value)}
                className="rounded border border-slate-300 px-2 py-1"
              />
            </label>
            <button
              type="submit"
              disabled={busy || !file || needsReason}
              className="w-fit rounded border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100 disabled:opacity-50"
            >
              {assembled ? "Attach as amendment" : "Attach"}
            </button>
            {assembled && needsReason && (
              <span className="text-xs text-amber-900">Enter the amendment reason above first.</span>
            )}
          </form>
        )}
      </section>

      <CrossReferences
        paperId={id}
        binderId={paper.binder_id}
        xrefs={paper.xrefs}
        attachments={paper.attachments}
        busy={busy}
        run={run}
        canEdit={!assembled && !purged}
      />

      <section>
        <h2 className="text-lg font-semibold">Versions</h2>
        {paper.versions.length === 0 ? (
          <p className="mt-2 text-slate-500">No versions yet. Preparing the paper writes the first.</p>
        ) : (
          <table className="mt-3 w-full rounded border border-slate-200 bg-white text-sm">
            <thead className="text-left text-slate-600">
              <tr>
                <th className="px-3 py-2">Version</th>
                <th className="px-3 py-2">Prepared by</th>
                <th className="px-3 py-2">Reviewed by</th>
                <th className="px-3 py-2">Signed off by</th>
                <th className="px-3 py-2">Content hash</th>
              </tr>
            </thead>
            <tbody>
              {paper.versions.map((v) => (
                <tr key={v.version} className="border-t border-slate-100">
                  <td className="px-3 py-2">{v.version}</td>
                  <td className="px-3 py-2">{who(v.prepared_by, v.prepared_at)}</td>
                  <td className="px-3 py-2">{who(v.reviewed_by, v.reviewed_at)}</td>
                  <td className="px-3 py-2">{who(v.signed_off_by, v.signed_off_at)}</td>
                  <td className="px-3 py-2 font-mono text-xs">{v.content_hash.slice(0, 16)}…</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
