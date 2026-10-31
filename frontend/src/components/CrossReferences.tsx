import { useEffect, useState } from "react";

import { api, type Attachment, type Binder, type Xref } from "../api";
import { href } from "../router";

// Cross-references on one paper (spec 3B, 3E): out (this paper refers to something) and in
// (something refers to this paper). A reference names one target: another paper of this
// binder, a financial-statement line, or a document attached in this binder. The API checks
// paper and document targets and names a broken one; an FS line cannot be checked without
// the Spine (D21) and is shown as such. References are added and removed while the binder
// is open; assembly freezes them with the file.

type TargetKind = "paper" | "fs_line" | "document";

function targetOf(x: Xref) {
  if (x.to_wp) {
    return (
      <a href={href({ name: "paper", id: x.to_wp })} className="font-mono underline">
        {x.to_ref}
      </a>
    );
  }
  if (x.to_fs_line !== null) return <>FS line “{x.to_fs_line}”</>;
  if (x.to_attachment_id && x.to_filename) {
    return (
      <>
        document{" "}
        <a href={api.attachmentUrl(x.to_attachment_id)} className="underline">
          {x.to_filename}
        </a>
        {x.to_attachment_ref ? <span className="text-slate-500"> (filed on {x.to_attachment_ref})</span> : null}
      </>
    );
  }
  return <>document <code className="font-mono text-xs">{x.to_vault_doc}</code></>;
}

function sourceOf(x: Xref, paperId: string) {
  if (x.from_wp === paperId) return "this paper";
  return (
    <a href={href({ name: "paper", id: x.from_wp })} className="font-mono underline">
      {x.from_ref}
    </a>
  );
}

function Row({
  x,
  paperId,
  canEdit,
  busy,
  run,
}: {
  x: Xref;
  paperId: string;
  canEdit: boolean;
  busy: boolean;
  run: (action: () => Promise<unknown>) => Promise<boolean>;
}) {
  // Read from this paper. A row written here reads "this paper → target" (direction "to") or
  // "target → this paper" (direction "from"); a row written on another paper that points
  // here is read the other way round.
  const writtenHere = x.from_wp === paperId;
  const left = writtenHere ? "this paper" : sourceOf(x, paperId);
  const right = writtenHere ? targetOf(x) : "this paper";
  const arrow = x.direction === "to" ? "→" : "←";
  return (
    <li className="flex flex-wrap items-baseline justify-between gap-2 px-3 py-2" data-testid="xref">
      <span>
        {left} {arrow} {right}
        {x.target_amended ? (
          <span className="ml-2 rounded bg-amber-50 px-1.5 py-0.5 text-xs text-amber-900" data-testid="xref-amended">
            {x.target_amended}
          </span>
        ) : null}
        {x.broken ? (
          <span className="ml-2 rounded bg-red-50 px-1.5 py-0.5 text-xs text-red-800" data-testid="xref-broken">
            broken: {x.broken}
          </span>
        ) : x.checked ? null : (
          <span className="ml-2 rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600">
            not checked (no Spine)
          </span>
        )}
        <span className="ml-2 text-xs text-slate-500">
          {x.created_by} {x.created_at}
        </span>
      </span>
      {canEdit && writtenHere && (
        <button
          type="button"
          disabled={busy}
          onClick={() => void run(() => api.removeXref(x.id))}
          className="text-xs underline disabled:opacity-50"
        >
          Remove
        </button>
      )}
    </li>
  );
}

export function CrossReferences({
  paperId,
  binderId,
  xrefs,
  attachments,
  busy,
  run,
  canEdit,
}: {
  paperId: string;
  binderId: string;
  xrefs: Xref[];
  attachments: Attachment[];
  busy: boolean;
  run: (action: () => Promise<unknown>) => Promise<boolean>;
  canEdit: boolean;
}) {
  const [kind, setKind] = useState<TargetKind>("paper");
  const [direction, setDirection] = useState<"to" | "from">("to");
  const [toWp, setToWp] = useState("");
  const [fsLine, setFsLine] = useState("");
  const [doc, setDoc] = useState("");
  const [binder, setBinder] = useState<Binder | null>(null);
  const [binderError, setBinderError] = useState<string | null>(null);

  const out = xrefs.filter((x) => x.outgoing);
  const inbound = xrefs.filter((x) => !x.outgoing);
  const broken = xrefs.filter((x) => x.broken).length;

  // The binder's papers are fetched once, when the paper picker is first shown.
  useEffect(() => {
    if (kind !== "paper" || binder || binderError) return;
    let cancelled = false;
    api
      .getBinder(binderId)
      .then((b) => {
        if (!cancelled) setBinder(b);
      })
      .catch((e: Error) => {
        if (!cancelled) setBinderError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [kind, binder, binderError, binderId]);
  const candidates = (binder?.sections ?? [])
    .flatMap((s) => s.papers)
    .filter((p) => p.id !== paperId);

  const target =
    kind === "paper"
      ? toWp
      : kind === "fs_line"
        ? fsLine.trim()
        : doc.trim();

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!target) return;
    void run(async () => {
      await api.addXref(paperId, {
        to_wp: kind === "paper" ? toWp : null,
        to_fs_line: kind === "fs_line" ? fsLine.trim() : null,
        to_vault_doc: kind === "document" ? doc.trim() : null,
        direction,
      });
      setToWp("");
      setFsLine("");
      setDoc("");
    });
  };

  const list = (title: string, rows: Xref[], empty: string) => (
    <div>
      <h3 className="mt-3 text-sm font-medium text-slate-700">{title}</h3>
      {rows.length === 0 ? (
        <p className="mt-1 text-sm text-slate-500">{empty}</p>
      ) : (
        <ul className="mt-1 divide-y divide-slate-100 rounded border border-slate-200 bg-white text-sm">
          {rows.map((x) => (
            <Row key={x.id} x={x} paperId={paperId} canEdit={canEdit} busy={busy} run={run} />
          ))}
        </ul>
      )}
    </div>
  );

  return (
    <section>
      <h2 className="text-lg font-semibold">
        Cross-references{" "}
        <span className={`text-sm font-normal ${broken ? "text-red-800" : "text-slate-500"}`} data-testid="xref-summary">
          {broken ? `${broken} broken — blocks assembly` : `${out.length} out, ${inbound.length} in`}
        </span>
      </h2>
      <p className="text-xs text-slate-500">
        Where this paper's figures come from and go to: other papers, financial-statement lines,
        source documents. A reference to a paper or document is checked; one to an FS line is
        not, since the Spine is not part of this product.
      </p>
      {list("Out — this paper refers to", out, "No outgoing references.")}
      {list("In — refers to this paper", inbound, "Nothing refers to this paper.")}

      {canEdit && (
        <form onSubmit={submit} className="mt-3 grid max-w-xl gap-2 text-sm">
          <div className="flex flex-wrap gap-3">
            <label className="grid gap-1">
              Direction
              <select
                value={direction}
                onChange={(e) => setDirection(e.target.value as "to" | "from")}
                className="rounded border border-slate-300 px-2 py-1"
              >
                <option value="to">This paper refers to the target</option>
                <option value="from">The target refers to this paper</option>
              </select>
            </label>
            <label className="grid gap-1">
              Target
              <select
                value={kind}
                onChange={(e) => setKind(e.target.value as TargetKind)}
                className="rounded border border-slate-300 px-2 py-1"
              >
                <option value="paper">Paper in this binder</option>
                <option value="fs_line">Financial-statement line</option>
                <option value="document">Document attached in this binder</option>
              </select>
            </label>
          </div>
          {kind === "paper" && (
            <label className="grid gap-1">
              Paper
              <select
                value={toWp}
                onChange={(e) => setToWp(e.target.value)}
                className="rounded border border-slate-300 px-2 py-1"
                data-testid="xref-paper"
              >
                <option value="">{binderError ? `Could not load papers: ${binderError}` : "Choose a paper…"}</option>
                {candidates.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.ref} {p.title}
                  </option>
                ))}
              </select>
            </label>
          )}
          {kind === "fs_line" && (
            <label className="grid gap-1">
              FS line (as it appears in the financial statements)
              <input
                value={fsLine}
                maxLength={200}
                onChange={(e) => setFsLine(e.target.value)}
                className="rounded border border-slate-300 px-2 py-1"
              />
            </label>
          )}
          {kind === "document" && (
            <label className="grid gap-1">
              Document id (this paper's attachments are offered; any document attached in this
              binder is accepted)
              <input
                list="xref-docs"
                value={doc}
                onChange={(e) => setDoc(e.target.value)}
                className="rounded border border-slate-300 px-2 py-1 font-mono text-xs"
              />
              <datalist id="xref-docs">
                {attachments.map((a) => (
                  <option key={a.id} value={a.vault_doc_id}>
                    {a.filename}
                  </option>
                ))}
              </datalist>
            </label>
          )}
          <button
            type="submit"
            disabled={busy || !target}
            className="w-fit rounded border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100 disabled:opacity-50"
          >
            Add reference
          </button>
        </form>
      )}
    </section>
  );
}
