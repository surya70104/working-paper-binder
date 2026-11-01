import { useState } from "react";

import { api, type Binder } from "../api";
import { useAction } from "../useAction";

// Review levels, configurable per engagement (spec 3D "Levels: preparer → senior → manager →
// partner → EQR, configurable per engagement"; D33). The preparer is always level one, from the
// prepared version; the levels listed here follow in order; sign-off closes the chain. The list
// can change while the binder is open and before any level review is recorded; after the first
// level review anywhere in the binder it is frozen for good, at the service and the database.

export const SPEC_LEVELS = ["senior", "manager", "partner", "EQR"];

export function ReviewLevelsCard({ binder, onChanged }: { binder: Binder; onChanged: () => Promise<void> }) {
  const configured = binder.review_levels ?? [];
  const [text, setText] = useState(configured.join(", "));
  const { run, busy, error } = useAction(onChanged);
  const open = binder.state === "open";
  const editable = open && !binder.review_levels_frozen;
  const parsed = text
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  const dirty = parsed.join("|") !== configured.join("|");

  return (
    <section className="rounded border border-slate-200 bg-white p-4" data-testid="review-levels-card">
      <h2 className="text-lg font-semibold">Review levels</h2>
      <p className="mt-1 text-sm text-slate-600">
        The chain every paper follows: <span className="font-mono text-xs">preparer</span>
        {configured.map((level) => (
          <span key={level}>
            {" → "}
            <span className="font-mono text-xs">{level}</span>
          </span>
        ))}
        {configured.length === 0 && (
          <>
            {" → "}
            <span className="font-mono text-xs">review</span>
          </>
        )}
        {" → "}
        <span className="font-mono text-xs">sign-off</span>
        {configured.length === 0 && (
          <span className="ml-2 text-xs text-slate-500" data-testid="review-levels-default">
            (no levels configured: one review, then sign-off)
          </span>
        )}
      </p>
      {binder.review_levels_frozen ? (
        <p className="mt-2 text-xs text-slate-600" data-testid="review-levels-frozen">
          Frozen: a level review has been recorded on a paper of this binder, so the chain the
          reviews were made under cannot change (spec 3D, 3F).
        </p>
      ) : !open ? (
        <p className="mt-2 text-xs text-slate-600" data-testid="review-levels-frozen">
          The binder is {binder.state}: the review levels are frozen with the file.
        </p>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void run(() => api.setReviewLevels(binder.id, parsed.length ? parsed : null));
          }}
          className="mt-3 grid max-w-xl gap-2 text-sm"
        >
          <label className="grid gap-1">
            Review levels after the preparer, in order, comma separated
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={SPEC_LEVELS.join(", ")}
              className="rounded border border-slate-300 px-2 py-1 font-mono text-xs"
            />
          </label>
          <p className="text-xs text-slate-500">
            The specification names {SPEC_LEVELS.join(", ")}; the firm chooses per engagement.
            &quot;preparer&quot; is always first and is not listed. Leave empty for one review, then
            sign-off. Editable until the first level review is recorded.
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="submit"
              disabled={busy || !dirty}
              className="w-fit rounded border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100 disabled:opacity-50"
            >
              Save review levels
            </button>
            {busy && <span className="text-xs text-slate-600">Working…</span>}
          </div>
        </form>
      )}
      {error && (
        <p role="alert" className="mt-2 text-sm text-red-700">
          {error}
        </p>
      )}
    </section>
  );
}
