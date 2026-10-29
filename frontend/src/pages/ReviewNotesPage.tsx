import { useCallback, useEffect, useState } from "react";

import { api, NOTE_STATE_LABEL, STATUS_LABEL, type BinderReviewNote } from "../api";
import { href } from "../router";
import { useAction } from "../useAction";

// Screen 3 (spec 5): what is open, raised by whom, assigned to whom, blocking what.
export function ReviewNotesPage({ id }: { id: string }) {
  const [notes, setNotes] = useState<BinderReviewNote[] | null>(null);
  const [showCleared, setShowCleared] = useState(false);

  const load = useCallback(async () => {
    setNotes(await api.listBinderNotes(id));
  }, [id]);
  const { error, setError } = useAction(load);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load, setError]);

  if (error && !notes) {
    return (
      <p role="alert" className="text-red-700">
        {error}
      </p>
    );
  }
  if (!notes) return <p className="text-slate-500">Loading…</p>;

  const open = notes.filter((n) => n.open);
  const shown = showCleared ? notes : open;

  return (
    <div className="space-y-6">
      <section>
        <p className="text-sm text-slate-500">
          <a href="#/" className="hover:underline">
            Binders
          </a>{" "}
          /{" "}
          <a href={href({ name: "binder", id })} className="hover:underline">
            Binder
          </a>{" "}
          / Review notes
        </p>
        <h1 className="text-xl font-semibold">Review notes</h1>
        <p className="text-sm text-slate-600" data-testid="summary">
          {open.length === 0
            ? "No open review notes. Nothing blocks sign-off or assembly on this account."
            : `${open.length} open review note${open.length === 1 ? "" : "s"} on ${
                new Set(open.map((n) => n.ref)).size
              } paper${new Set(open.map((n) => n.ref)).size === 1 ? "" : "s"}: each blocks that paper's sign-off and the binder's assembly.`}
        </p>
        <label className="mt-2 flex items-center gap-2 text-sm">
          <input type="checkbox" checked={showCleared} onChange={(e) => setShowCleared(e.target.checked)} />
          Show cleared notes
        </label>
      </section>

      {shown.length === 0 ? (
        <p className="text-sm text-slate-500">{showCleared ? "No review notes." : "No open review notes."}</p>
      ) : (
        <table className="w-full rounded border border-slate-200 bg-white text-sm">
          <thead className="text-left text-slate-600">
            <tr>
              <th className="px-3 py-2">Paper</th>
              <th className="px-3 py-2">Note</th>
              <th className="px-3 py-2">State</th>
              <th className="px-3 py-2">Raised by</th>
              <th className="px-3 py-2">Assigned to</th>
              <th className="px-3 py-2">Blocking</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((n) => (
              <tr key={n.note_id} className="border-t border-slate-100" data-testid="note-row">
                <td className="px-3 py-2">
                  <a href={href({ name: "paper", id: n.wp_id })} className="underline">
                    <span className="font-mono">{n.ref}</span> {n.title}
                  </a>
                </td>
                <td className="px-3 py-2">{n.text}</td>
                <td className="px-3 py-2">{NOTE_STATE_LABEL[n.state]}</td>
                <td className="px-3 py-2">{n.raised_by}</td>
                <td className="px-3 py-2">{n.assigned_to ?? "—"}</td>
                <td className="px-3 py-2">
                  {n.open
                    ? `sign-off of ${n.ref} (${STATUS_LABEL[n.paper_status]}) and assembly`
                    : "nothing"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
