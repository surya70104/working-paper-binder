import { useCallback, useEffect, useState } from "react";

import { api, type BinderState, type Departure, type Discussion } from "../api";
import { useAction } from "../useAction";

// The discussions and departures logs (spec 2, 3H, 4). Entries are recorded, never edited
// or deleted. After assembly an entry needs an amendment reason and the file must be
// re-assembled before it is produced again; a purged binder takes no entries.
// "Including TCWG" is met by the participants list: write the role after the name.

export const TCWG_HINT =
  'One participant per line, role after the name, e.g. "R. Mehta (TCWG, Audit Committee Chair)"';

// One participant per line: a role such as "(TCWG, Audit Committee Chair)" holds commas, so
// commas never separate participants.
function splitLines(text: string): string[] {
  return text
    .split(/\r?\n/)
    .map((s) => s.trim())
    .filter(Boolean);
}

export function BinderRecords({ binderId, state }: { binderId: string; state: BinderState }) {
  const [discussions, setDiscussions] = useState<Discussion[] | null>(null);
  const [departures, setDepartures] = useState<Departure[] | null>(null);
  const [discussion, setDiscussion] = useState({ date: "", participants: "", matter: "", outcome: "" });
  const [departure, setDeparture] = useState({
    requirement: "",
    reason: "",
    alternative_procedure: "",
    approved_by: "",
  });
  const [amendmentReason, setAmendmentReason] = useState("");

  const load = useCallback(async () => {
    const [d, p] = await Promise.all([api.listDiscussions(binderId), api.listDepartures(binderId)]);
    setDiscussions(d);
    setDepartures(p);
  }, [binderId]);
  const { run, busy, error, setError } = useAction(load);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load, setError]);

  const assembled = state === "assembled";
  const purged = state === "purged";
  const needsReason = assembled && amendmentReason.trim().length === 0;
  const reasonOrUndefined = assembled ? amendmentReason.trim() : undefined;

  const submitDiscussion = (e: React.FormEvent) => {
    e.preventDefault();
    void run(async () => {
      await api.recordDiscussion(binderId, {
        date: discussion.date,
        participants: splitLines(discussion.participants),
        matter: discussion.matter.trim(),
        outcome: discussion.outcome.trim() || null,
        amendment_reason: reasonOrUndefined,
      });
      setDiscussion({ date: "", participants: "", matter: "", outcome: "" });
    });
  };

  const submitDeparture = (e: React.FormEvent) => {
    e.preventDefault();
    void run(async () => {
      await api.recordDeparture(binderId, {
        requirement: departure.requirement.trim(),
        reason: departure.reason.trim(),
        alternative_procedure: departure.alternative_procedure.trim(),
        approved_by: departure.approved_by.trim() || null,
        amendment_reason: reasonOrUndefined,
      });
      setDeparture({ requirement: "", reason: "", alternative_procedure: "", approved_by: "" });
    });
  };

  const input = "rounded border border-slate-300 px-2 py-1";
  const button =
    "w-fit rounded border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100 disabled:opacity-50";

  return (
    <>
      {error && (
        <p role="alert" className="text-sm text-red-700">
          {error}
        </p>
      )}
      {assembled && (
        <section className="rounded border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          <p>
            This file is assembled. A discussion or departure recorded now is an amendment: it
            needs a reason, is written to the audit trail, and the file must be re-assembled
            before it is produced again.
          </p>
          <label className="mt-2 grid max-w-xl gap-1">
            Amendment reason
            <input
              value={amendmentReason}
              onChange={(e) => setAmendmentReason(e.target.value)}
              className={input}
              data-testid="records-amendment-reason"
            />
          </label>
        </section>
      )}

      <section>
        <h2 className="text-lg font-semibold">Discussions</h2>
        <p className="text-xs text-slate-500">
          Significant matters, with whom, when, including those charged with governance (TCWG).
          Recorded, never edited.
        </p>
        {discussions === null ? (
          <p className="mt-2 text-sm text-slate-500">Loading…</p>
        ) : discussions.length === 0 ? (
          <p className="mt-2 text-sm text-slate-500">No discussions recorded.</p>
        ) : (
          <ul className="mt-2 divide-y divide-slate-100 rounded border border-slate-200 bg-white text-sm">
            {discussions.map((d) => (
              <li key={d.id} className="px-3 py-2" data-testid="discussion">
                <p>
                  <span className="font-medium">{d.date}</span> · {d.participants.join("; ")}
                </p>
                <p className="mt-1">{d.matter}</p>
                {d.outcome && <p className="mt-1 text-slate-700">Outcome: {d.outcome}</p>}
                <p className="mt-1 text-xs text-slate-500">
                  recorded by {d.recorded_by} {d.recorded_at}
                </p>
              </li>
            ))}
          </ul>
        )}
        {!purged && (
          <form onSubmit={submitDiscussion} className="mt-3 grid max-w-xl gap-2 text-sm">
            <label className="grid gap-1">
              Date
              <input
                type="date"
                required
                value={discussion.date}
                onChange={(e) => setDiscussion({ ...discussion, date: e.target.value })}
                className={input}
              />
            </label>
            <label className="grid gap-1">
              Participants
              <textarea
                required
                rows={3}
                value={discussion.participants}
                onChange={(e) => setDiscussion({ ...discussion, participants: e.target.value })}
                className={input}
                placeholder={TCWG_HINT}
              />
            </label>
            <p className="text-xs text-slate-500">{TCWG_HINT}</p>
            <label className="grid gap-1">
              Matter
              <textarea
                required
                rows={2}
                value={discussion.matter}
                onChange={(e) => setDiscussion({ ...discussion, matter: e.target.value })}
                className={input}
              />
            </label>
            <label className="grid gap-1">
              Outcome (optional)
              <textarea
                rows={2}
                value={discussion.outcome}
                onChange={(e) => setDiscussion({ ...discussion, outcome: e.target.value })}
                className={input}
              />
            </label>
            <button type="submit" disabled={busy || needsReason} className={button}>
              {assembled ? "Record discussion as amendment" : "Record discussion"}
            </button>
          </form>
        )}
      </section>

      <section>
        <h2 className="text-lg font-semibold">Departures</h2>
        <p className="text-xs text-slate-500">
          A departure from a relevant requirement: which requirement, why, and the alternative
          procedure performed. Recorded, never edited.
        </p>
        {departures === null ? (
          <p className="mt-2 text-sm text-slate-500">Loading…</p>
        ) : departures.length === 0 ? (
          <p className="mt-2 text-sm text-slate-500">No departures recorded.</p>
        ) : (
          <ul className="mt-2 divide-y divide-slate-100 rounded border border-slate-200 bg-white text-sm">
            {departures.map((d) => (
              <li key={d.id} className="px-3 py-2" data-testid="departure">
                <p className="font-medium">{d.requirement}</p>
                <p className="mt-1">Reason: {d.reason}</p>
                <p className="mt-1">Alternative procedure: {d.alternative_procedure}</p>
                <p className="mt-1 text-xs text-slate-500">
                  {d.approved_by ? `approved by ${d.approved_by} · ` : "not yet approved · "}
                  recorded by {d.recorded_by} {d.recorded_at}
                </p>
              </li>
            ))}
          </ul>
        )}
        {!purged && (
          <form onSubmit={submitDeparture} className="mt-3 grid max-w-xl gap-2 text-sm">
            <label className="grid gap-1">
              Requirement departed from
              <input
                required
                value={departure.requirement}
                onChange={(e) => setDeparture({ ...departure, requirement: e.target.value })}
                className={input}
              />
            </label>
            <label className="grid gap-1">
              Reason
              <textarea
                required
                rows={2}
                value={departure.reason}
                onChange={(e) => setDeparture({ ...departure, reason: e.target.value })}
                className={input}
              />
            </label>
            <label className="grid gap-1">
              Alternative procedure performed
              <textarea
                required
                rows={2}
                value={departure.alternative_procedure}
                onChange={(e) => setDeparture({ ...departure, alternative_procedure: e.target.value })}
                className={input}
              />
            </label>
            <label className="grid gap-1">
              Approved by (optional)
              <input
                value={departure.approved_by}
                onChange={(e) => setDeparture({ ...departure, approved_by: e.target.value })}
                className={input}
              />
            </label>
            <button type="submit" disabled={busy || needsReason} className={button}>
              {assembled ? "Record departure as amendment" : "Record departure"}
            </button>
          </form>
        )}
      </section>
    </>
  );
}
