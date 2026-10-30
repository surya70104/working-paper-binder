import { useCallback, useEffect, useState } from "react";

import { api, BLOCKER_LABEL, type AssemblyStatus, type Verification } from "../api";
import { href } from "../router";
import { useAction } from "../useAction";

// Screen 5 (spec 5): the blockers, the Assemble action, the manifest, Produce file, and
// the retention clock with Purge. Every rule is enforced by the API; this page shows it.
export function AssemblyPage({ id }: { id: string }) {
  const [status, setStatus] = useState<AssemblyStatus | null>(null);
  const [verification, setVerification] = useState<Verification | null>(null);
  const [confirmPurge, setConfirmPurge] = useState(false);

  const load = useCallback(async () => {
    setStatus(await api.getAssembly(id));
  }, [id]);
  const { run, busy, error, setError } = useAction(load);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load, setError]);

  if (error && !status) {
    return (
      <p role="alert" className="text-red-700">
        {error}
      </p>
    );
  }
  if (!status) return <p className="text-slate-500">Loading…</p>;

  const blocked = status.blockers.length > 0;
  const assembled = status.state === "assembled";
  const purged = status.state === "purged";

  return (
    <div className="space-y-8">
      <section>
        <p className="text-sm text-slate-500">
          <a href="#/" className="hover:underline">
            Binders
          </a>{" "}
          /{" "}
          <a href={href({ name: "binder", id })} className="hover:underline">
            Binder
          </a>{" "}
          / Assembly &amp; retention
        </p>
        <h1 className="text-xl font-semibold">Assembly &amp; retention</h1>
        <p className="text-sm text-slate-600">
          State: <span data-testid="state">{status.state}</span>
          {status.assembly_due
            ? ` · assembly due ${status.assembly_due}${
                status.days_to_assembly !== null
                  ? status.days_to_assembly >= 0
                    ? ` (${status.days_to_assembly} days left)`
                    : ` (${-status.days_to_assembly} days overdue)`
                  : ""
              }`
            : " · report not yet dated"}
        </p>
        {error && (
          <p role="alert" className="mt-2 text-sm text-red-700">
            {error}
          </p>
        )}
      </section>

      <section className="rounded border border-slate-200 bg-white p-4">
        <h2 className="text-lg font-semibold">Blockers</h2>
        {blocked ? (
          <ul className="mt-2 list-disc pl-5 text-sm text-amber-900" data-testid="blockers">
            {status.blockers.map((b, i) => (
              <li key={i}>
                {BLOCKER_LABEL[b.kind] ?? b.kind}
                {b.ref ? ` ${b.ref}` : ""}: {b.detail}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-sm text-green-800">Nothing blocks assembly.</p>
        )}
        <p className="mt-3 text-xs text-slate-500">Not checked (Pass 2):</p>
        <ul className="list-disc pl-5 text-xs text-slate-500">
          {status.not_checked.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
        {!purged && (
          <div className="mt-3 flex items-center gap-3">
            <button
              type="button"
              disabled={busy || blocked}
              onClick={() => void run(() => api.assemble(id))}
              className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white hover:bg-slate-700 disabled:opacity-50"
            >
              {assembled ? "Re-assemble after amendments" : "Assemble"}
            </button>
            {busy && <span className="text-sm text-slate-600">Working…</span>}
          </div>
        )}
      </section>

      {status.assembly_hash && (
        <section className="rounded border border-slate-200 bg-white p-4">
          <h2 className="text-lg font-semibold">Manifest</h2>
          <p className="mt-1 text-sm">
            Assembled {status.assembled_at} · file hash{" "}
            <code className="rounded bg-slate-100 px-1 font-mono text-xs" data-testid="hash">
              {status.assembly_hash}
            </code>
          </p>
          {status.manifest && (
            <table className="mt-3 w-full text-sm">
              <thead className="text-left text-slate-600">
                <tr>
                  <th className="px-2 py-1">Ref</th>
                  <th className="px-2 py-1">Title</th>
                  <th className="px-2 py-1">Version</th>
                  <th className="px-2 py-1">Content hash</th>
                  <th className="px-2 py-1">Attachments</th>
                </tr>
              </thead>
              <tbody>
                {status.manifest.papers.map((p) => (
                  <tr key={p.ref} className="border-t border-slate-100">
                    <td className="px-2 py-1 font-mono">{p.ref}</td>
                    <td className="px-2 py-1">{p.title}</td>
                    <td className="px-2 py-1">{p.version ?? "—"}</td>
                    <td className="px-2 py-1 font-mono text-xs">{p.content_hash?.slice(0, 16)}…</td>
                    <td className="px-2 py-1">{p.attachments.map((a) => a.filename).join(", ") || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <button
              type="button"
              disabled={busy}
              onClick={() =>
                void run(async () => {
                  setVerification(await api.verify(id));
                })
              }
              className="rounded border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100 disabled:opacity-50"
            >
              Verify hashes
            </button>
            {!purged && status.matches_recorded_manifest && (
              <a
                href={api.produceUrl(id)}
                className="rounded border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100"
              >
                Produce file (zip)
              </a>
            )}
            {!purged && !status.matches_recorded_manifest && (
              <span className="text-sm text-amber-900" data-testid="produce-blocked">
                The file has changed since assembly (amendments pending). Re-assemble before
                producing, so the manifest describes what is produced.
              </span>
            )}
          </div>
          {verification && (
            <div className="mt-3 text-sm" data-testid="verification">
              <p className={verification.ok ? "text-green-800" : "text-red-700"}>
                {verification.ok
                  ? "Every recorded hash reproduces."
                  : "Verification found mismatches."}
                {verification.current_matches_assembled
                  ? " The file matches its assembled manifest."
                  : " The file has changed since assembly; re-assemble to record the amendments."}
              </p>
              <ul className="mt-1 list-disc pl-5 text-xs">
                {verification.checks
                  .filter((c) => !c.ok)
                  .map((c) => (
                    <li key={c.item} className="text-red-700">
                      {c.item}: {c.detail}
                    </li>
                  ))}
              </ul>
            </div>
          )}
        </section>
      )}

      <section className="rounded border border-slate-200 bg-white p-4">
        <h2 className="text-lg font-semibold">Retention</h2>
        <p className="mt-1 text-sm">
          {status.retention_until
            ? `Retain until ${status.retention_until} (report date + 7 years).`
            : "The retention clock starts with the report date."}
        </p>
        {purged ? (
          <p className="mt-2 text-sm text-slate-700">
            Content purged after retention. Paper and version metadata with their hashes
            remain; attachments are gone.
          </p>
        ) : (
          <div className="mt-2 flex items-center gap-3">
            {!confirmPurge ? (
              <button
                type="button"
                disabled={busy || !status.purge_allowed}
                onClick={() => setConfirmPurge(true)}
                className="rounded border border-red-300 px-3 py-1.5 text-sm text-red-800 hover:bg-red-50 disabled:opacity-50"
              >
                Purge content
              </button>
            ) : (
              <>
                <span className="text-sm text-red-800">
                  This destroys every attachment of this file. Paper and version metadata stay.
                </span>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void run(() => api.purge(id))}
                  className="rounded bg-red-700 px-3 py-1.5 text-sm text-white hover:bg-red-800 disabled:opacity-50"
                >
                  Confirm purge
                </button>
                <button
                  type="button"
                  onClick={() => setConfirmPurge(false)}
                  className="text-sm underline"
                >
                  Cancel
                </button>
              </>
            )}
            {!status.purge_allowed && !confirmPurge && (
              <span className="text-xs text-slate-500">
                {assembled ? "Available once retention expires." : "Available for an assembled file after retention."}
              </span>
            )}
          </div>
        )}
      </section>

      <section>
        <h2 className="text-lg font-semibold">Audit trail</h2>
        {status.events.length === 0 ? (
          <p className="mt-2 text-sm text-slate-500">No events yet.</p>
        ) : (
          <ul className="mt-2 divide-y divide-slate-100 rounded border border-slate-200 bg-white text-sm">
            {status.events.map((e) => (
              <li key={e.id} className="px-3 py-2" data-testid="event">
                <span className="font-medium">{e.kind}</span> · {e.actor} ·{" "}
                <span className="text-slate-500">{e.at}</span>
                {e.reason ? <> · {e.reason}</> : null}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
