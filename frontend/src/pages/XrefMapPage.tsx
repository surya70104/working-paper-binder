import { useCallback, useEffect, useState } from "react";

import { api, STATUS_LABEL, type MapPaper, type XrefMap } from "../api";
import { href } from "../router";

// Screen 4 (spec 5): the cross-reference map, financial statement line → lead schedule →
// working paper → source document, with broken and amended links flagged. Every node links
// to its paper or document, so the chain is clickable both ways (spec 3E).

function Badge({ tone, children }: { tone: "red" | "amber" | "grey"; children: React.ReactNode }) {
  const cls =
    tone === "red"
      ? "bg-red-50 text-red-800"
      : tone === "amber"
        ? "bg-amber-50 text-amber-900"
        : "bg-slate-100 text-slate-600";
  return <span className={`ml-2 rounded px-1.5 py-0.5 text-xs ${cls}`}>{children}</span>;
}

function PaperNode({ paper, depth }: { paper: MapPaper; depth: number }) {
  return (
    <li className="mt-1" data-testid={paper.role === "lead_schedule" ? "map-lead" : "map-paper"}>
      <div className="flex flex-wrap items-baseline gap-1 text-sm">
        <span className="text-xs text-slate-500">{paper.role === "lead_schedule" ? "lead schedule" : "working paper"}</span>
        <a href={href({ name: "paper", id: paper.id })} className="font-mono underline">
          {paper.ref}
        </a>
        <span>{paper.title}</span>
        <span className="text-xs text-slate-500">· {STATUS_LABEL[paper.status as keyof typeof STATUS_LABEL] ?? paper.status}</span>
        {paper.link?.broken && (
          <Badge tone="red">
            <span data-testid="map-broken">broken: {paper.link.broken}</span>
          </Badge>
        )}
        {paper.link?.amended && (
          <Badge tone="amber">
            <span data-testid="map-amended">{paper.link.amended}</span>
          </Badge>
        )}
        {paper.link && !paper.link.checked && <Badge tone="grey">not checked</Badge>}
      </div>
      {paper.documents.length > 0 && (
        <ul className="ml-6 mt-1 space-y-1 text-sm">
          {paper.documents.map((d) => (
            <li key={d.xref_id} data-testid="map-document">
              <span className="text-xs text-slate-500">source document</span>{" "}
              {d.attachment_id && d.filename ? (
                <a href={api.attachmentUrl(d.attachment_id)} className="underline">
                  {d.filename}
                </a>
              ) : (
                <code className="font-mono text-xs">{d.doc_id}</code>
              )}
              {d.filed_on_ref && <span className="text-xs text-slate-500"> (filed on {d.filed_on_ref})</span>}
              {d.broken && (
                <Badge tone="red">
                  <span data-testid="map-broken">broken: {d.broken}</span>
                </Badge>
              )}
            </li>
          ))}
        </ul>
      )}
      {paper.papers.length > 0 && (
        <ul className="ml-6 border-l border-slate-200 pl-3">
          {paper.papers.map((p) => (
            <PaperNode key={p.link?.xref_id ?? p.id} paper={p} depth={depth + 1} />
          ))}
        </ul>
      )}
    </li>
  );
}

export function XrefMapPage({ id }: { id: string }) {
  const [map, setMap] = useState<XrefMap | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setMap(await api.getXrefMap(id));
  }, [id]);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load]);

  if (error) {
    return (
      <p role="alert" className="text-red-700">
        {error}
      </p>
    );
  }
  if (!map) return <p className="text-slate-500">Loading…</p>;

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
          / Cross-reference map
        </p>
        <h1 className="text-xl font-semibold">Cross-reference map</h1>
        <p className="text-sm text-slate-600">
          Financial statement line → lead schedule → working paper → source document.
        </p>
        <p className="mt-2 text-sm" data-testid="map-summary">
          {map.total_references} reference(s) ·{" "}
          <span className={map.broken ? "text-red-800" : ""}>{map.broken} broken</span> ·{" "}
          <span className={map.amended ? "text-amber-900" : ""}>{map.amended} with an amended target</span> ·{" "}
          <span className="text-slate-600">{map.unchecked} not checked</span>
        </p>
        {!map.available && (
          <p className="mt-2 rounded bg-amber-50 px-3 py-2 text-sm text-amber-900" role="status">
            Financial-statement lines cannot be checked: {map.reason}. References to FS lines are
            shown as written and counted as not checked.
          </p>
        )}
      </section>

      <section>
        <h2 className="text-lg font-semibold">Financial statement lines</h2>
        {map.lines.length === 0 ? (
          <p className="mt-2 text-sm text-slate-500">No paper refers to a financial statement line yet.</p>
        ) : (
          <ul className="mt-2 space-y-3">
            {map.lines.map((line) => (
              <li key={line.head_id} className="rounded border border-slate-200 bg-white p-3" data-testid="map-line">
                <p className="font-medium">
                  {line.label ?? line.head_id}
                  <code className="ml-2 font-mono text-xs text-slate-500">{line.head_id}</code>
                  {line.current && <span className="ml-2 text-sm text-slate-600">₹{line.current}</span>}
                  {!line.known && (
                    <Badge tone={map.available ? "red" : "grey"}>
                      {map.available ? "not a line of the linked version" : "not checked"}
                    </Badge>
                  )}
                </p>
                <ul className="mt-1">
                  {line.papers.map((p) => (
                    <PaperNode key={p.link?.xref_id ?? p.id} paper={p} depth={1} />
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        )}
      </section>

      {map.beyond_depth.length > 0 && (
        <section data-testid="map-beyond">
          <h2 className="text-lg font-semibold">Papers further down a chain</h2>
          <p className="mt-1 text-sm text-slate-600">
            These papers are tied to a financial statement line through the papers above, but sit
            deeper than the {map.max_depth} levels the map draws. Their links and documents are
            checked like any other.
          </p>
          <ul className="mt-2 rounded border border-slate-200 bg-white p-3">
            {map.beyond_depth.map((p) => (
              <PaperNode key={p.link?.xref_id ?? p.id} paper={p} depth={map.max_depth + 1} />
            ))}
          </ul>
        </section>
      )}

      <section>
        <h2 className="text-lg font-semibold">Papers not tied to any financial statement line</h2>
        {map.unattached.length === 0 ? (
          <p className="mt-2 text-sm text-slate-500">Every paper is reachable from a financial statement line.</p>
        ) : (
          <ul className="mt-2 rounded border border-slate-200 bg-white p-3">
            {map.unattached.map((p) => (
              <PaperNode key={p.id} paper={p} depth={1} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
