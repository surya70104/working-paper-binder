import { useState } from "react";

import { api, type BinderState, type Generation, type ReferenceChanges } from "../api";
import { useAction } from "../useAction";

// Spec 3C (D31): a paper a module produced "arrives complete, with its inputs and its
// citations, and nobody retypes anything". This panel shows where it came from, read-only:
// the source and module, the run, when it was generated and delivered, what the spec names
// for the source (formula and seed; periods and thresholds; benchmark, band and Spine
// figures; source-row citations), then the inputs and citations as delivered.

export const SOURCE_LABEL: Record<string, string> = {
  materiality: "Materiality",
  sampling: "Sampling",
  analytical_review: "Analytical Review",
  workmind: "WorkMind",
  spine: "Financial Spine",
};

function Value({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <span className="text-slate-400">—</span>;
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return <span>{String(value)}</span>;
  }
  return <pre className="overflow-x-auto whitespace-pre-wrap font-mono text-xs">{JSON.stringify(value, null, 2)}</pre>;
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1 sm:grid-cols-[12rem_1fr]">
      <dt className="text-slate-500">{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function SourceBlock({ generation }: { generation: Generation }) {
  const block = generation.payload[generation.source] as Record<string, unknown> | undefined;
  if (!block) return null;
  switch (generation.source) {
    case "sampling":
      return (
        <>
          <Row label="Formula">
            <code className="font-mono" data-testid="gen-formula">
              {String(block.formula)}
            </code>
          </Row>
          <Row label="Seed">
            <code className="font-mono" data-testid="gen-seed">
              {String(block.seed)}
            </code>
          </Row>
        </>
      );
    case "analytical_review": {
      const periods = block.periods as { current?: string; prior?: string } | undefined;
      return (
        <>
          <Row label="Periods">
            <span data-testid="gen-periods">
              {periods?.current} against {periods?.prior}
            </span>
          </Row>
          <Row label="Thresholds used">
            <Value value={block.thresholds} />
          </Row>
        </>
      );
    }
    case "materiality": {
      const figures = block.spine_figures as { version_id?: string; figures?: unknown } | undefined;
      return (
        <>
          <Row label="Benchmark">
            <Value value={block.benchmark} />
          </Row>
          <Row label="Band">
            <Value value={block.band} />
          </Row>
          <Row label="Figures from the Spine">
            <div className="space-y-1">
              <p className="text-xs text-slate-500" data-testid="gen-spine-check">
                Spine version <code className="font-mono">{figures?.version_id}</code>
                {generation.spine_figures_check === "verified" && (
                  <span className="ml-2 rounded bg-green-50 px-1.5 py-0.5 text-green-800">verified against the linked version</span>
                )}
                {generation.spine_figures_check === "not_checked" && (
                  <span className="ml-2 rounded bg-slate-100 px-1.5 py-0.5 text-slate-600">not checked: the binder is not linked to a Spine version</span>
                )}
              </p>
              <Value value={figures?.figures} />
            </div>
          </Row>
        </>
      );
    }
    case "workmind":
      return (
        <Row label="Source-row citations">
          <Value value={block.source_row_citations} />
        </Row>
      );
    case "spine": {
      // Stage E (D32): the version the paper was built from and what the Spine served; the
      // full tables are the paper's result, so only the shape is repeated here.
      const lines = (block.lines as unknown[] | undefined) ?? [];
      const ledgers = (block.ledgers as unknown[] | undefined) ?? [];
      const without = (block.heads_without_ledgers as string[] | undefined) ?? [];
      const adjustments = (block.adjustments as unknown[] | undefined) ?? [];
      return (
        <>
          <Row label="Spine version">
            <span data-testid="gen-spine-version">
              {String(block.version_label)} <code className="font-mono text-xs">{String(block.version_id)}</code>
              {block.locked_at ? <span className="text-slate-500"> locked {String(block.locked_at)}</span> : null}
            </span>
          </Row>
          <Row label="Version hash">
            <code className="break-all font-mono text-xs">{String(block.version_hash)}</code>
          </Row>
          <Row label="Paper kind">
            <span data-testid="gen-spine-kind">
              {block.kind === "lead_schedule" ? `lead schedule for area ${String(block.area)}` : "adjustment chain"}
            </span>
          </Row>
          <Row label="Served">
            <span data-testid="gen-spine-counts">
              {block.kind === "lead_schedule"
                ? `${lines.length} financial statement line(s), ${ledgers.length} ledger row(s), ${without.length} head(s) with no ledger entry, ${adjustments.length} adjustment(s) touching the area`
                : `${adjustments.length} adjustment(s) in every status, and the uncorrected schedule as served`}
            </span>
          </Row>
        </>
      );
    }
    default:
      return (
        <Row label={generation.source}>
          <Value value={block} />
        </Row>
      );
  }
}

// Freshness of a Spine paper (Stage E, D32): current, stale or not checked, as the backend
// says. Stale is information, never a blocker. Regeneration is offered while the binder is
// open; it rewrites the Spine's fields, keeps the person's, appends a provenance row and moves
// only the references the Binder reliably owns. What it did to the references is shown.
function FreshnessBanner({
  generation,
  paperId,
  binderState,
  onChanged,
}: {
  generation: Generation;
  paperId?: string;
  binderState?: BinderState;
  onChanged?: () => Promise<void>;
}) {
  const [changes, setChanges] = useState<ReferenceChanges | null>(null);
  const { run, busy, error } = useAction(onChanged ?? (async () => undefined));
  const fresh = generation.freshness;
  if (generation.source !== "spine" || !fresh) return null;
  const open = binderState === "open";
  const regenerate = () =>
    void run(async () => {
      const result = await api.regeneratePaper(paperId ?? "");
      setChanges(result.regeneration.references);
    });
  if (fresh.state === "current") {
    return (
      <p className="mt-2 text-xs" data-testid="gen-freshness">
        <span className="rounded bg-green-50 px-1.5 py-0.5 text-green-800">current</span>{" "}
        <span className="text-slate-600">matches the binder&apos;s linked Spine version.</span>
        {changes && <ReferenceChangeList changes={changes} />}
      </p>
    );
  }
  const tone = fresh.state === "stale" ? "bg-amber-50 text-amber-900" : "bg-slate-100 text-slate-700";
  return (
    <div className={`mt-2 rounded px-3 py-2 text-sm ${tone}`} role="status" data-testid="gen-freshness">
      <p>
        <strong>{fresh.state === "stale" ? "Stale" : "Not checked"}:</strong> {fresh.detail}
      </p>
      {open ? (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={regenerate}
            className="rounded border border-slate-300 bg-white px-3 py-1 text-sm hover:bg-slate-100 disabled:opacity-50"
          >
            Regenerate from the linked version
          </button>
          <span className="text-xs">
            Rewrites the Spine&apos;s fields and returns the paper to draft; your objective, procedure and
            conclusion and every earlier version are kept. Only references the Binder wrote are moved.
          </span>
          {busy && <span className="text-xs">Working…</span>}
        </div>
      ) : (
        <p className="mt-1 text-xs" data-testid="gen-no-regenerate">
          Regeneration is offered while the binder is open; the paper is kept as it was frozen. This
          is information in the assembly status, never a blocker.
        </p>
      )}
      {error && (
        <p role="alert" className="mt-1 text-xs text-red-700">
          {error}
        </p>
      )}
      {changes && <ReferenceChangeList changes={changes} />}
    </div>
  );
}

function ReferenceChangeList({ changes }: { changes: ReferenceChanges }) {
  const item = (label: string, values: string[]) => (
    <li>
      {label}: {values.length ? values.join(", ") : "none"}
    </li>
  );
  return (
    <ul className="mt-2 list-disc pl-5 text-xs text-slate-700" data-testid="gen-regeneration">
      <li>Regenerated. References:</li>
      {item("added", changes.added)}
      {item("removed (Binder-written, target no longer served)", changes.removed)}
      {item("kept", changes.kept)}
      {item("for your review (not written by the Binder; target no longer served)", changes.for_review)}
    </ul>
  );
}

export function GeneratedPanel({
  generation,
  status,
  paperId,
  binderState,
  onChanged,
}: {
  generation: Generation;
  status?: string;
  paperId?: string;
  binderState?: BinderState;
  onChanged?: () => Promise<void>;
}) {
  const [showRaw, setShowRaw] = useState(false);
  const label = SOURCE_LABEL[generation.source] ?? generation.source;
  return (
    <section className="rounded border border-indigo-200 bg-indigo-50/40 p-4 text-sm" data-testid="generated-panel">
      <h2 className="text-lg font-semibold">Generated by {label}</h2>
      <FreshnessBanner generation={generation} paperId={paperId} binderState={binderState} onChanged={onChanged} />
      <p className="mt-1 text-xs text-slate-600">
        This paper arrived complete from a module, with its inputs and citations. Its fields are
        not retyped here; a correction comes from the module. The conclusion is written by a person.
      </p>
      {status === "draft" && (
        <p className="mt-1 text-xs text-slate-600" data-testid="gen-sequence">
          Supporting attachments are uploaded separately, after intake and before preparation.
          Review the generated content and its attachments together before preparing: preparing
          writes version 1 covering both.
        </p>
      )}
      <dl className="mt-3 grid gap-2">
        <Row label="Module">
          <span data-testid="gen-module">
            {generation.module}
            {generation.module_version && <span className="text-slate-500"> {generation.module_version}</span>}
          </span>
        </Row>
        <Row label="Run">
          {generation.run_id ? <code className="font-mono">{generation.run_id}</code> : <span className="text-slate-400">no run id given</span>}
        </Row>
        <Row label="Generated at">{generation.generated_at}</Row>
        <Row label="Delivered">
          {generation.received_by} <span className="text-slate-500">{generation.received_at}</span>
        </Row>
        {generation.run_verification && (
          <Row label="Run verified">
            <span data-testid="gen-run-verified">
              {String(generation.run_verification.status)} by {String(generation.run_verification.accepted_by ?? "—")}{" "}
              <span className="text-slate-500">{String(generation.run_verification.accepted_at ?? "")}</span>, read from
              WorkMind at {String(generation.run_verification.checked_at ?? "")}
            </span>
          </Row>
        )}
        <SourceBlock generation={generation} />
        <Row label="Fields hash at intake">
          <code className="break-all font-mono text-xs">{generation.content_hash_at_intake}</code>
        </Row>
      </dl>
      <button
        type="button"
        onClick={() => setShowRaw((v) => !v)}
        aria-expanded={showRaw}
        className="mt-3 rounded border border-slate-300 px-2 py-1 text-xs hover:bg-white"
      >
        {showRaw ? "Hide inputs and citations" : "Show inputs and citations"}
      </button>
      {showRaw && (
        <dl className="mt-2 grid gap-2" data-testid="gen-raw">
          <Row label="Inputs">
            <Value value={generation.payload.inputs} />
          </Row>
          <Row label="Citations">
            <Value value={generation.payload.citations} />
          </Row>
        </dl>
      )}
    </section>
  );
}
