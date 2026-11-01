import { useCallback, useEffect, useState } from "react";

import { api, type BinderState, type SpineLink, type SpineVersion } from "../api";
import { useAction } from "../useAction";

// The Financial Spine link (spec 3A "tying to the Financial Spine"; D29). A binder ties to
// one Spine engagement and one of its versions. The link can be set, changed or cleared
// while the binder is open; assembly needs a locked version; after assembly the link is
// frozen with the file. The Binder only ever reads the Spine.
export function SpineLinkCard({
  binderId,
  state,
  onChanged,
}: {
  binderId: string;
  state: BinderState;
  onChanged: () => Promise<void>;
}) {
  const [link, setLink] = useState<SpineLink | null>(null);
  const [engagementId, setEngagementId] = useState("");
  const [versions, setVersions] = useState<SpineVersion[] | null>(null);
  const [versionId, setVersionId] = useState("");

  const load = useCallback(async () => {
    const current = await api.getSpineLink(binderId);
    setLink(current);
    setEngagementId(current.engagement_id ?? "");
    setVersionId(current.version_id ?? "");
    await onChanged();
  }, [binderId, onChanged]);
  const { run, busy, error, setError } = useAction(load);
  useEffect(() => {
    api
      .getSpineLink(binderId)
      .then((current) => {
        setLink(current);
        setEngagementId(current.engagement_id ?? "");
        setVersionId(current.version_id ?? "");
      })
      .catch((e: Error) => setError(e.message));
  }, [binderId, setError]);

  if (!link) return <section className="text-sm text-slate-500">Loading Financial Spine link…</section>;

  const open = state === "open";
  const input = "rounded border border-slate-300 px-2 py-1 font-mono text-xs";
  const button =
    "rounded border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100 disabled:opacity-50";

  // Loading the versions is a read for the form, not a change to the binder, so it does not
  // go through `run`: a reload would put the stored link back into the fields being edited.
  const loadVersions = () => {
    setError(null);
    api
      .listSpineVersions(engagementId.trim())
      .then(setVersions)
      .catch((e: Error) => setError(e.message));
  };

  const save = () =>
    void run(() =>
      api.setSpineLink(binderId, {
        spine_engagement_id: engagementId.trim() || null,
        spine_version_id: versionId.trim() || null,
      }),
    );

  const clear = () =>
    void run(() => api.setSpineLink(binderId, { spine_engagement_id: null, spine_version_id: null }));

  return (
    <section className="rounded border border-slate-200 bg-white p-4" data-testid="spine-card">
      <h2 className="text-lg font-semibold">Financial Spine</h2>
      {!link.configured ? (
        <p className="mt-1 text-sm text-slate-500" data-testid="spine-unconfigured">
          No Financial Spine is configured for this Binder (OAK_SPINE_URL). The file can be
          assembled without one; references to financial-statement lines stay unchecked.
        </p>
      ) : link.engagement_id === null ? (
        <p className="mt-1 text-sm text-slate-500">Not linked to a Spine engagement.</p>
      ) : (
        <div className="mt-1 text-sm" data-testid="spine-link">
          <p>
            Engagement <code className="font-mono text-xs">{link.engagement_id}</code>
            {link.engagement ? ` · ${link.engagement.label} · year end ${link.engagement.financial_year_end ?? "—"}` : ""}
          </p>
          <p>
            Version{" "}
            {link.version_id ? <code className="font-mono text-xs">{link.version_id}</code> : "not chosen"}
            {link.version ? (
              <>
                {" "}· {link.version.label}
                {link.version.is_locked ? (
                  <span className="ml-2 rounded bg-green-50 px-1.5 py-0.5 text-xs text-green-800">
                    locked {link.version.locked_at}
                  </span>
                ) : (
                  <span className="ml-2 rounded bg-amber-50 px-1.5 py-0.5 text-xs text-amber-900">
                    not locked — blocks assembly
                  </span>
                )}
              </>
            ) : null}
          </p>
          {!link.reachable && link.reason && (
            <p className="mt-1 text-amber-900" role="status">
              The Spine could not be read: {link.reason}
            </p>
          )}
        </div>
      )}
      {error && (
        <p role="alert" className="mt-2 text-sm text-red-700">
          {error}
        </p>
      )}
      {link.configured && open && (
        <div className="mt-3 grid max-w-xl gap-2 text-sm">
          <label className="grid gap-1">
            Spine engagement id
            <input
              value={engagementId}
              onChange={(e) => {
                setEngagementId(e.target.value);
                setVersions(null);
                setVersionId("");
              }}
              className={input}
            />
          </label>
          <div className="flex flex-wrap items-end gap-2">
            <button type="button" disabled={busy || !engagementId.trim()} onClick={loadVersions} className={button}>
              Load versions
            </button>
            {versions && (
              <label className="grid gap-1">
                Version
                <select
                  value={versionId}
                  onChange={(e) => setVersionId(e.target.value)}
                  className="rounded border border-slate-300 px-2 py-1"
                  data-testid="spine-version"
                >
                  <option value="">No version</option>
                  {versions.map((v) => (
                    <option key={v.version_id} value={v.version_id}>
                      {v.version_no ?? "?"} · {v.label} · {v.is_locked ? "locked" : "not locked"}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <button type="button" disabled={busy || !engagementId.trim()} onClick={save} className={button}>
              Save link
            </button>
            {link.engagement_id && (
              <button type="button" disabled={busy} onClick={clear} className="text-sm underline disabled:opacity-50">
                Clear link
              </button>
            )}
          </div>
        </div>
      )}
      {link.configured && !open && link.engagement_id && (
        <p className="mt-2 text-xs text-slate-500">The link is frozen with the assembled file.</p>
      )}
    </section>
  );
}
