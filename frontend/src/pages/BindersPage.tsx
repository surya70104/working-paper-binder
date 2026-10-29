import { useCallback, useEffect, useState } from "react";

import { api, type BinderSummary, type Template } from "../api";
import { href, navigate } from "../router";
import { useAction } from "../useAction";

export function BindersPage() {
  const [binders, setBinders] = useState<BinderSummary[] | null>(null);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [engagement, setEngagement] = useState("");
  const [template, setTemplate] = useState("statutory");
  const [reportDate, setReportDate] = useState("");

  const load = useCallback(async () => {
    setBinders(await api.listBinders());
  }, []);
  const { run, busy, error, setError } = useAction(load);

  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
    api.listTemplates().then(setTemplates, (e: Error) => setError(e.message));
  }, [load, setError]);

  function create(event: React.FormEvent) {
    event.preventDefault();
    void run(async () => {
      const binder = await api.createBinder(engagement, template, reportDate || null);
      navigate({ name: "binder", id: binder.id });
    });
  }

  return (
    <div className="space-y-8">
      <section>
        <h1 className="text-xl font-semibold">Binders</h1>
        {error && (
          <p role="alert" className="mt-2 text-sm text-red-700">
            {error}
          </p>
        )}
        {binders === null ? (
          <p className="mt-2 text-slate-500">Loading…</p>
        ) : binders.length === 0 ? (
          <p className="mt-2 text-slate-500">No binders yet.</p>
        ) : (
          <ul className="mt-3 divide-y divide-slate-200 rounded border border-slate-200 bg-white">
            {binders.map((b) => (
              <li key={b.id} className="flex items-baseline justify-between px-4 py-2">
                <a href={href({ name: "binder", id: b.id })} className="font-medium hover:underline">
                  {b.engagement}
                </a>
                <span className="text-sm text-slate-500">
                  {b.template.replace("_", " ")} · {b.state}
                  {b.report_date ? ` · report dated ${b.report_date}` : ""}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h2 className="text-lg font-semibold">New binder</h2>
        <form onSubmit={create} className="mt-3 grid max-w-xl gap-3">
          <label className="grid gap-1 text-sm">
            Engagement
            <input
              required
              value={engagement}
              onChange={(e) => setEngagement(e.target.value)}
              className="rounded border border-slate-300 px-2 py-1"
            />
          </label>
          <label className="grid gap-1 text-sm">
            Index template
            <select
              value={template}
              onChange={(e) => setTemplate(e.target.value)}
              className="rounded border border-slate-300 px-2 py-1"
            >
              {(templates.length ? templates : [{ name: "statutory", label: "Statutory audit" }]).map(
                (t) => (
                  <option key={t.name} value={t.name}>
                    {t.label}
                  </option>
                ),
              )}
            </select>
          </label>
          <label className="grid gap-1 text-sm">
            Report date (optional; starts the 60-day and 7-year clocks)
            <input
              type="date"
              value={reportDate}
              onChange={(e) => setReportDate(e.target.value)}
              className="rounded border border-slate-300 px-2 py-1"
            />
          </label>
          <button
            type="submit"
            disabled={busy}
            className="w-fit rounded bg-slate-900 px-3 py-1.5 text-sm text-white hover:bg-slate-700 disabled:opacity-50"
          >
            Create binder
          </button>
        </form>
      </section>
    </div>
  );
}
