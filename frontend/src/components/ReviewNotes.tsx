import { useState } from "react";

import { api, NOTE_STATE_LABEL, type ReviewNote } from "../api";

// Review notes on one paper (spec 3D): raise, then assign, respond, clear, in that order.
// Every step is recorded; an open note blocks sign-off and assembly. The API enforces all of
// it; this component only offers the next step for each note.
export function ReviewNotes({
  paperId,
  notes,
  busy,
  run,
  canRaise,
}: {
  paperId: string;
  notes: ReviewNote[];
  busy: boolean;
  run: (action: () => Promise<unknown>) => Promise<boolean>;
  canRaise: boolean;
}) {
  const [text, setText] = useState("");
  const [assignee, setAssignee] = useState<Record<string, string>>({});
  const [response, setResponse] = useState<Record<string, string>>({});
  const open = notes.filter((n) => n.open).length;

  return (
    <section>
      <h2 className="text-lg font-semibold">
        Review notes{" "}
        <span className={`text-sm font-normal ${open ? "text-amber-900" : "text-slate-500"}`} data-testid="open-notes">
          {open === 0 ? "none open" : `${open} open — blocks sign-off and assembly`}
        </span>
      </h2>
      <p className="text-xs text-slate-500">raised → assigned → responded → cleared. A note is open until it is cleared.</p>

      {notes.length === 0 ? (
        <p className="mt-2 text-sm text-slate-500">No review notes.</p>
      ) : (
        <ul className="mt-2 divide-y divide-slate-100 rounded border border-slate-200 bg-white text-sm">
          {notes.map((n) => (
            <li key={n.note_id} className="px-3 py-2" data-testid="note">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <span>
                  <span className={`mr-2 rounded px-1.5 py-0.5 text-xs ${n.open ? "bg-amber-100 text-amber-900" : "bg-green-100 text-green-900"}`}>
                    {NOTE_STATE_LABEL[n.state]}
                  </span>
                  {n.text}
                </span>
                <span className="text-xs text-slate-500">
                  raised by {n.raised_by} · {n.raised_at}
                  {n.assigned_to ? ` · assigned to ${n.assigned_to}` : ""}
                  {n.cleared_by ? ` · cleared by ${n.cleared_by}` : ""}
                </span>
              </div>
              {n.response && (
                <p className="mt-1 text-slate-700">
                  <span className="text-slate-500">Response:</span> {n.response}
                </p>
              )}
              {n.state === "raised" && (
                <form
                  className="mt-2 flex items-end gap-2"
                  onSubmit={(e) => {
                    e.preventDefault();
                    void run(() => api.assignNote(n.note_id, assignee[n.note_id] ?? ""));
                  }}
                >
                  <label className="grid gap-1 text-xs">
                    Assign to
                    <input
                      value={assignee[n.note_id] ?? ""}
                      onChange={(e) => setAssignee({ ...assignee, [n.note_id]: e.target.value })}
                      className="rounded border border-slate-300 px-2 py-1"
                    />
                  </label>
                  <button type="submit" disabled={busy || !(assignee[n.note_id] ?? "").trim()} className="rounded border border-slate-300 px-2 py-1 text-xs disabled:opacity-50">
                    Assign
                  </button>
                </form>
              )}
              {n.state === "assigned" && (
                <form
                  className="mt-2 flex items-end gap-2"
                  onSubmit={(e) => {
                    e.preventDefault();
                    void run(() => api.respondNote(n.note_id, response[n.note_id] ?? ""));
                  }}
                >
                  <label className="grid flex-1 gap-1 text-xs">
                    Response
                    <input
                      value={response[n.note_id] ?? ""}
                      onChange={(e) => setResponse({ ...response, [n.note_id]: e.target.value })}
                      className="rounded border border-slate-300 px-2 py-1"
                    />
                  </label>
                  <button type="submit" disabled={busy || !(response[n.note_id] ?? "").trim()} className="rounded border border-slate-300 px-2 py-1 text-xs disabled:opacity-50">
                    Respond
                  </button>
                </form>
              )}
              {n.state === "responded" && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void run(() => api.clearNote(n.note_id))}
                  className="mt-2 rounded bg-slate-900 px-2 py-1 text-xs text-white disabled:opacity-50"
                >
                  Clear
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      {canRaise && (
        <form
          className="mt-3 flex items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void run(async () => {
              await api.raiseNote(paperId, text);
              setText("");
            });
          }}
        >
          <label className="grid flex-1 gap-1 text-sm">
            New review note
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              className="rounded border border-slate-300 px-2 py-1"
            />
          </label>
          <button type="submit" disabled={busy || !text.trim()} className="rounded border border-slate-300 px-3 py-1.5 text-sm disabled:opacity-50">
            Raise note
          </button>
        </form>
      )}
    </section>
  );
}
