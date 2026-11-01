# Generated-paper intake — contract for module authors

**31 October 2026 · Pass 2 Stage D (architecture D31).** How Materiality, Sampling,
Analytical Review and, later, WorkMind deliver a working paper to the Binder. Spec §3C: "A
paper produced by a module arrives complete, with its inputs and its citations, and nobody
retypes anything."

The worked examples are the fixtures under `backend\tests\fixtures\generated\`:
`materiality.json`, `sampling.json`, `analytical_review.json`, `workmind.json`. Their contents
are **examples of shape, not requirements**: the Binder checks presence of what the spec names
and keeps everything else verbatim.

## The call

```
POST /api/binders/{binder_id}/generated-papers
Content-Type: application/json
Authorization: Bearer <OAK_INTAKE_CREDENTIAL>        # only when the Binder has one configured
X-Authenticated-User: <module identity>              # set by the proxy under OAK_AUTH=header
```

`201 Created` returns the paper as the paper endpoint does, including `generated`. The paper
is a **draft**: a person prepares it and the review chain signs it off. The module is never
the preparer.

## The body

```jsonc
{
  "paper": {                       // exactly the fields a hand-made paper has (spec 3B)
    "ref": "D-3", "section": "D", "title": "…", "sa_refs": ["SA 530"],
    "objective": "…", "procedure": "…", "population_sample": "…",
    "result": "…", "conclusion": "…"          // conclusion: see the source rules
  },
  "generated": {
    "source": "sampling",          // materiality | sampling | analytical_review | workmind | spine
    "module": "oak_sampling",      // the module's name
    "module_version": "1.4.0",     // optional
    "run_id": "…",                 // required for workmind, optional otherwise; unique per source
    "generated_at": "2026-10-31T10:15:00+05:30",
    "inputs": { … },               // what the module computed from — non-empty, kept verbatim
    "citations": [ … ],            // where its figures came from — non-empty, kept verbatim
    "sampling": { … }              // exactly one source block, matching "source"
  }
}
```

The whole `generated` block must fit `OAK_MAX_PROVENANCE_BYTES` (default 1 MiB). The source
blocks are strict: a key the contract does not name is refused.

## Per-source rules (from the spec's words)

| Source | Block | Required | Checked |
|---|---|---|---|
| `materiality` | `materiality` | `benchmark`, `band`, `spine_figures.version_id` (UUID), `spine_figures.figures` — each present and non-empty | `version_id` must be the binder's linked Spine version; refused otherwise. Unlinked binder: kept and marked `not_checked` |
| `sampling` | `sampling` | `formula` (text), `seed` (integer or text) | both must appear **verbatim in the paper's text** (title, objective, procedure, population and sample, result or conclusion): the spec says "printed on it" |
| `analytical_review` | `analytical_review` | `periods.current`, `periods.prior` (different), `thresholds` (non-empty) | — |
| `workmind` | `workmind` | `run_id` on the block above, `source_row_citations[]` each with `source` and `row` (optional `detail`); **no `conclusion`** (spec §7) | validated in full, then **refused with 501** until WorkMind exists and an accepted run can be verified |
| `spine` | — | — | refused (422): Spine-produced papers (lead schedules, the adjustment chain) are built by the Binder's own Spine-papers action from the linked, locked version (Stage E, D32), never delivered through this endpoint |

Materiality, Sampling and Analytical Review may deliver a `conclusion`; a person may rewrite
it. WorkMind may not.

## After intake

- **Locked fields.** Title, section, SA references, objective, procedure, population and
  sample and result are the module's; the Binder refuses a change to them and names the
  module. A correction is a regeneration. The conclusion is a person's to write.
- **Attachments (decision 10).** Supporting attachments are uploaded separately through the existing attachment API after intake creates the draft paper, but before the preparer completes preparation. The preparer must be able to review the generated content and its supporting attachments before proceeding.
  The sequence is: intake creates the draft → the module (or a person) uploads each
  supporting file through `POST /api/papers/{id}/attachments`, using the paper id the
  intake response returns → the preparer opens the paper, reviews the generated content
  and the attachments together → prepare writes version 1, whose body lists the
  attachments by hash. A paper prepared before its files arrive would return to draft
  when a file is attached, so upload everything first.
- **Provenance.** Every version body of the paper carries `generated`: source, module, run,
  times, who delivered it, the module fields' hash at intake, and the whole block as
  delivered. The archive's `versions/NNNN.json` carry it; `paper.json` says `generated_by`.
  `GET /api/papers/{id}/generation` returns the same.

## Refusals

| Status | Why |
|---|---|
| 401 | the intake credential is missing or wrong |
| 403 | under header auth, the identity is not in `OAK_INTAKE_IDENTITIES` (or none are listed) |
| 404 | no such binder |
| 409 | the binder is assembled; the paper reference is already used; the run id was already received for that source |
| 413 | the `generated` block is over the size cap |
| 422 | a required field is missing or empty, a block does not match the source, an unknown key, formula or seed not printed on the paper, Spine figures from another version, a WorkMind conclusion |
| 501 | a valid WorkMind delivery, until the module exists |
