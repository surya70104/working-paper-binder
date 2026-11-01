import { useCallback, useEffect, useState } from "react";

import { api, STATUS_LABEL, type Binder, type RequiredPaper } from "../api";
import { BinderRecords } from "../components/BinderRecords";
import { SOURCE_LABEL } from "../components/GeneratedPanel";
import { SpineLinkCard } from "../components/SpineLinkCard";
import { ReviewLevelsCard } from "../components/ReviewLevelsCard";
import { SpinePapersCard } from "../components/SpinePapersCard";
import { href, navigate } from "../router";
import { useAction } from "../useAction";

export function countdownText(binder: Binder): string {
  if (binder.assembly_due === null || binder.days_to_assembly === null) {
    return "Report not yet dated: the 60-day assembly clock has not started.";
  }
  const n = binder.days_to_assembly;
  if (n < 0) return `Assembly was due ${binder.assembly_due}: ${-n} days overdue.`;
  if (n === 0) return `Assembly is due today, ${binder.assembly_due}.`;
  return `Assembly due ${binder.assembly_due}: ${n} days left.`;
}

export function BinderPage({ id }: { id: string }) {
  const [binder, setBinder] = useState<Binder | null>(null);
  const [reportDate, setReportDate] = useState("");
  // sa_refs is typed as the preparer sees it (comma separated); the index template's
  // references for a missing paper prefill it (spec 3B "SA reference(s)"), editable before
  // the paper is created.
  const [draft, setDraft] = useState({ ref: "", section: "A", title: "", sa_refs: "" });

  const load = useCallback(async () => {
    const b = await api.getBinder(id);
    setBinder(b);
    setReportDate(b.report_date ?? "");
  }, [id]);
  const { run, busy, error, setError } = useAction(load);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load, setError]);

  function createPaper(event: React.FormEvent) {
    event.preventDefault();
    void run(async () => {
      const { sa_refs, ...fields } = draft;
      const refs = sa_refs
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      const paper = await api.createPaper(id, { ...fields, sa_refs: refs });
      navigate({ name: "paper", id: paper.id });
    });
  }

  function prefill(required: RequiredPaper) {
    setDraft({
      ref: required.ref,
      section: required.section,
      title: required.title,
      sa_refs: required.sa_refs.join(", "),
    });
  }

  if (error && !binder) {
    return (
      <p role="alert" className="text-red-700">
        {error}
      </p>
    );
  }
  if (!binder) return <p className="text-slate-500">Loading…</p>;

  const open = binder.state === "open" && !busy;

  return (
    <div className="space-y-8">
      <section>
        <p className="text-sm text-slate-500">
          <a href="#/" className="hover:underline">
            Binders
          </a>{" "}
          / {binder.engagement}
        </p>
        <h1 className="text-xl font-semibold">{binder.engagement}</h1>
        <p className="text-sm text-slate-600">
          {binder.template_label} · {binder.state} ·{" "}
          <a href={href({ name: "review-notes", id })} className="underline">
            Review notes
          </a>{" "}
          ·{" "}
          <a href={href({ name: "xref-map", id })} className="underline">
            Cross-reference map
          </a>{" "}
          ·{" "}
          <a href={href({ name: "assembly", id })} className="underline">
            Assembly &amp; retention
          </a>
        </p>
        {error && (
          <p role="alert" className="mt-2 text-sm text-red-700">
            {error}
          </p>
        )}
        <div className="mt-4 grid gap-3 rounded border border-slate-200 bg-white p-4 md:grid-cols-2">
          <div>
            <p className="font-medium">{countdownText(binder)}</p>
            <p className="text-sm text-slate-600">
              {binder.retention_until
                ? `Retain until ${binder.retention_until} (report date + 7 years).`
                : "Retention clock starts with the report date."}
            </p>
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void run(() => api.setReportDate(id, reportDate || null));
            }}
            className="flex items-end gap-2"
          >
            <label className="grid gap-1 text-sm">
              Report date
              <input
                type="date"
                value={reportDate}
                disabled={!open}
                onChange={(e) => setReportDate(e.target.value)}
                className="rounded border border-slate-300 px-2 py-1"
              />
            </label>
            <button
              type="submit"
              disabled={!open}
              className="rounded border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100 disabled:opacity-50"
            >
              Set
            </button>
          </form>
        </div>
        <p
          className={`mt-3 rounded px-3 py-2 text-sm ${
            binder.missing_required > 0 ? "bg-amber-50 text-amber-900" : "bg-green-50 text-green-900"
          }`}
        >
          Missing required papers: <strong>{binder.missing_required}</strong>
          {binder.missing_required > 0 ? " (blocks assembly)" : " — the index is complete"}
        </p>
      </section>

      <section>
        <h2 className="text-lg font-semibold">Index</h2>
        <ul className="mt-3 space-y-3">
          {binder.sections
            .filter((s) => s.papers.length > 0 || s.missing.length > 0)
            .map((s) => (
              <li key={s.code} className="rounded border border-slate-200 bg-white">
                <h3 className="border-b border-slate-100 px-4 py-2 font-medium">
                  {s.code} · {s.name}
                </h3>
                <ul className="divide-y divide-slate-100">
                  {s.papers.map((p) => (
                    <li key={p.id} className="flex items-baseline justify-between px-4 py-2">
                      <a href={href({ name: "paper", id: p.id })} className="hover:underline">
                        <span className="font-mono text-sm">{p.ref}</span> {p.title}
                        {p.generated_by && (
                          <span
                            className="ml-2 rounded bg-indigo-50 px-1.5 py-0.5 text-xs text-indigo-900"
                            data-testid="generated-mark"
                          >
                            generated · {SOURCE_LABEL[p.generated_by] ?? p.generated_by}
                          </span>
                        )}
                      </a>
                      <span className="text-sm text-slate-500">{STATUS_LABEL[p.status]}</span>
                    </li>
                  ))}
                  {s.missing.map((m) => (
                    <li
                      key={m.ref}
                      className="flex items-baseline justify-between px-4 py-2 text-amber-900"
                    >
                      <span>
                        <span className="font-mono text-sm">{m.ref}</span> {m.title} — missing
                      </span>
                      <button
                        type="button"
                        disabled={!open}
                        onClick={() => prefill(m)}
                        className="text-sm underline disabled:opacity-50"
                      >
                        Create
                      </button>
                    </li>
                  ))}
                </ul>
              </li>
            ))}
        </ul>
        {binder.sections.every((s) => s.papers.length === 0 && s.missing.length === 0) && (
          <p className="mt-2 text-slate-500">No papers yet.</p>
        )}
      </section>

      <SpineLinkCard binderId={id} state={binder.state} onChanged={load} />

      <SpinePapersCard
        binderId={id}
        state={binder.state}
        onChanged={load}
        refreshKey={`${binder.spine_engagement_id ?? ""}/${binder.spine_version_id ?? ""}/${binder.state}`}
      />

      <ReviewLevelsCard binder={binder} onChanged={load} />

      <BinderRecords binderId={id} state={binder.state} />

      <section>
        <h2 className="text-lg font-semibold">New working paper</h2>
        <form onSubmit={createPaper} className="mt-3 grid max-w-xl gap-3">
          <div className="grid grid-cols-[1fr_auto] gap-3">
            <label className="grid gap-1 text-sm">
              Reference (stable, never reused)
              <input
                required
                value={draft.ref}
                disabled={!open}
                onChange={(e) => setDraft({ ...draft, ref: e.target.value })}
                className="rounded border border-slate-300 px-2 py-1 font-mono"
              />
            </label>
            <label className="grid gap-1 text-sm">
              Section
              <select
                value={draft.section}
                disabled={!open}
                onChange={(e) => setDraft({ ...draft, section: e.target.value })}
                className="rounded border border-slate-300 px-2 py-1"
              >
                {binder.sections.map((s) => (
                  <option key={s.code} value={s.code}>
                    {s.code} · {s.name}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label className="grid gap-1 text-sm">
            Title
            <input
              required
              value={draft.title}
              disabled={!open}
              onChange={(e) => setDraft({ ...draft, title: e.target.value })}
              className="rounded border border-slate-300 px-2 py-1"
            />
          </label>
          <label className="grid gap-1 text-sm">
            SA references (comma separated; prefilled from the index template)
            <input
              value={draft.sa_refs}
              disabled={!open}
              onChange={(e) => setDraft({ ...draft, sa_refs: e.target.value })}
              className="rounded border border-slate-300 px-2 py-1 font-mono text-xs"
            />
          </label>
          <button
            type="submit"
            disabled={!open}
            className="w-fit rounded bg-slate-900 px-3 py-1.5 text-sm text-white hover:bg-slate-700 disabled:opacity-50"
          >
            Create paper
          </button>
        </form>
      </section>
    </div>
  );
}
